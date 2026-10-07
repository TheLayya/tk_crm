import html
import re
import httpx
import asyncio
import logging
import string
import time
import random
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Optional, Dict, Any
from urllib.parse import quote
from socksio.exceptions import SOCKSError
from app.models.monitor import MonitorProxy

logger = logging.getLogger(__name__)


ACCOUNT_NOT_FOUND = "ACCOUNT_NOT_FOUND: TikTok 明确提示找不到此账号（可能已改名、删除或不可用）"
VERIFICATION_REQUIRED = "VERIFICATION_REQUIRED: TikTok 返回验证页，采集端未获取到账号页面，无法判断账号是否存在；请人工打开主页核实。"
RETRYABLE_ERROR_CODES = frozenset({"proxy_error", "timeout", "network_error", "rate_limited", "upstream_unavailable"})


def is_retryable_result(result: Dict[str, Any]) -> bool:
    if result.get("error_code"):
        return bool(result.get("retryable", result["error_code"] in RETRYABLE_ERROR_CODES))
    message = str(result.get("error") or "").lower()
    if any(marker in message for marker in ("account_not_found", "verification_required")):
        return False
    if "retryable_collection_failed" in message:
        return True
    if any(marker in message for marker in ("http 200", "非 json")):
        return False
    return any(marker in message for marker in ("timeout", "timed out", "proxy", "malformed reply", "connection", "network_error", "collection_interrupted", "http 429", "http 502", "http 503", "http 504"))


def _failure(error: str, code: str) -> Dict[str, Any]:
    return {"success": False, "data": None, "error": error, "error_code": code,
            "retryable": code in RETRYABLE_ERROR_CODES}


def _exception_result(exc: Exception, stage: str) -> Dict[str, Any]:
    if isinstance(exc, (httpx.ProxyError, SOCKSError)):
        return _failure(f"PROXY_ERROR: {stage}代理连接或协议异常，请检查代理类型和节点连通性", "proxy_error")
    if isinstance(exc, httpx.TimeoutException):
        return _failure(f"TIMEOUT: {stage}请求超时", "timeout")
    if isinstance(exc, httpx.TransportError):
        return _failure(f"NETWORK_ERROR: {stage}网络连接异常（{type(exc).__name__}）", "network_error")
    return _failure(f"SCRAPE_ERROR: {stage}采集异常（{type(exc).__name__}）", "scrape_error")


def _http_result(status: int, stage: str) -> Dict[str, Any]:
    code = "rate_limited" if status == 429 else "upstream_unavailable" if status in (502, 503, 504) else "http_error"
    return _failure(f"{stage} HTTP {status}", code)


def is_account_not_found_message(message: object) -> bool:
    text = str(message or "").strip().lower()
    return text in ("user not found", "user doesn't exist", "user does not exist") or any(phrase in text for phrase in (
        "couldn't find this account", "couldn’t find this account", "could not find this account",
        "找不到此账号", "找不到此帐号",
    ))


def is_verification_page(response: httpx.Response) -> bool:
    text = response.text.lower()
    return any(marker in text for marker in ("slardarwaf", "_wafchallengeid", "waf-aiso/", "verify you are human"))


class ScraperService:
    def __init__(self) -> None:
        self.timeout = 30
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://www.tiktok.com/',
        }

    def _build_proxy_url(self, proxy: MonitorProxy | None) -> Optional[str]:
        """构建代理URL字符串"""
        if not proxy:
            return None
        auth = f"{quote(proxy.username, safe='')}:{quote(proxy.password or '', safe='')}@" if proxy.username else ""
        host = f"[{proxy.host}]" if ":" in proxy.host and not proxy.host.startswith("[") else proxy.host
        return f"{proxy.proxy_type}://{auth}{host}:{proxy.port}"

    async def _get_with_retry(self, client: httpx.AsyncClient, url: str,
                              headers: dict[str, str], params: dict[str, Any] | None = None) -> httpx.Response:
        for attempt in range(3):
            response = None
            try:
                response = await client.get(url, headers=headers, params=params)
                if (response.status_code not in (429, 502, 503, 504)
                        or is_verification_page(response) or attempt == 2):
                    return response
                reason = f"HTTP {response.status_code}"
            except (httpx.TransportError, SOCKSError) as exc:
                if attempt == 2:
                    raise
                reason = type(exc).__name__
            delay = 2 ** attempt + random.uniform(0, 0.25)
            if response is not None and response.headers.get("Retry-After"):
                try:
                    retry_after = response.headers["Retry-After"]
                    try:
                        server_delay = float(retry_after)
                    except ValueError:
                        server_delay = (parsedate_to_datetime(retry_after) - datetime.now(timezone.utc)).total_seconds()
                    delay = max(delay, min(10.0, max(0.0, server_delay)))
                except (TypeError, ValueError, OverflowError):
                    pass
            logger.warning("TikTok request retry %s/3: %s; delay=%.2fs", attempt + 2, reason, delay)
            await asyncio.sleep(delay)
        raise RuntimeError("Retry budget exhausted")

    async def fetch_user_info(self, username: str, proxy: MonitorProxy | None = None,
                              timeout: float | None = None) -> Dict[str, Any]:
        """
        抓取TikTok用户信息。
        返回格式: {success: bool, data: dict | None, error: str | None}
        """
        proxy_url = self._build_proxy_url(proxy)
        proxies: dict[str | httpx.URL, str | httpx.URL | httpx.Proxy | None] | None = {"all://": proxy_url} if proxy_url else None

        try:
            async with httpx.AsyncClient(
                proxies=proxies,
                timeout=self.timeout if timeout is None else timeout,
                follow_redirects=True
            ) as client:
                # 尝试 TikTok web API (非官方)
                api_result = await self._try_web_api(client, username)
                if api_result['success']:
                    return api_result

                # 备用：主页数据解析；这是另一条路径，不重复请求业务性失败。
                result = await self._try_oembed_api(client, username)
                if result['success']:
                    return result

                if result.get('error_code') == 'verification_required' or api_result.get('error_code') == 'verification_required':
                    return _failure(VERIFICATION_REQUIRED, 'verification_required')
                if result.get('error_code') == 'account_not_found' or api_result.get('error_code') == 'account_not_found':
                    return _failure(ACCOUNT_NOT_FOUND, 'account_not_found')
                combined = dict(result)
                api_retryable = is_retryable_result(api_result)
                page_retryable = is_retryable_result(result)
                if api_retryable or page_retryable:
                    code = result.get('error_code') if page_retryable else api_result.get('error_code')
                    combined['error_code'] = code or 'network_error'
                    combined['retryable'] = True
                    combined['error'] = f"RETRYABLE_COLLECTION_FAILED: User API: {api_result.get('error')}; profile page: {result.get('error')}"
                else:
                    combined['error'] = f"User API: {api_result.get('error')}; profile page: {result.get('error')}"
                combined['causes'] = {'user_api': api_result.get('error_code'), 'profile_page': result.get('error_code')}
                return combined

        except Exception as e:
            result = _exception_result(e, '用户资料')
            logger.error("TikTok profile request failed: %s", result['error_code'])
            return result

    async def _try_web_api(self, client: httpx.AsyncClient, username: str) -> Dict[str, Any]:
        """尝试 TikTok 非官方 web API"""
        try:
            url = f"https://www.tiktok.com/api/user/detail/?uniqueId={username}&aid=1988&app_language=en&app_name=tiktok_web&device_platform=web_pc"
            response = await self._get_with_retry(client, url, self.headers)
            if is_verification_page(response):
                return _failure(VERIFICATION_REQUIRED, 'verification_required')

            if response.status_code == 200:
                try:
                    data = response.json()
                except ValueError:
                    return _failure('TikTok 用户接口返回非 JSON 内容，未获取到账号数据', 'invalid_response')

                if not isinstance(data, dict):
                    return _failure('TikTok 用户接口返回的 JSON 结构异常，未获取到账号数据', 'invalid_response')
                user_info = data.get('userInfo') or {}
                if not isinstance(user_info, dict) or not isinstance(user_info.get('user') or {}, dict) or not isinstance(user_info.get('stats') or {}, dict):
                    return _failure('TikTok 用户接口返回的账号字段结构异常', 'invalid_response')
                user = user_info.get('user') or {}
                stats = user_info.get('stats') or {}

                if is_account_not_found_message(data.get('statusMsg')) and not user.get('id'):
                    return _failure(ACCOUNT_NOT_FOUND, 'account_not_found')

                if user.get('id'):
                    # 解析注册时间（Unix 时间戳）
                    create_time = user.get('createTime')
                    account_created_at = None
                    if create_time:
                        try:
                            account_created_at = datetime.utcfromtimestamp(int(create_time))
                        except (TypeError, ValueError, OSError, OverflowError):
                            pass
                    return {
                        'success': True,
                        'data': {
                            'tiktok_id': user.get('id'),
                            'sec_uid': user.get('secUid'),
                            'nickname': user.get('nickname'),
                            'avatar_url': user.get('avatarMedium') or user.get('avatarLarger'),
                            'bio': user.get('signature'),
                            **({'follower_count': stats['followerCount']}
                               if isinstance(stats.get('followerCount'), int)
                               and not isinstance(stats['followerCount'], bool)
                               and stats['followerCount'] >= 0 else {}),
                            'following_count': stats.get('followingCount', 0),
                            'like_count': stats.get('heartCount', 0),
                            'video_count': stats.get('videoCount', 0),
                            'region': user.get('region'),
                            'account_created_at': account_created_at,
                        },
                        'error': None
                    }

                return _failure('TikTok 用户接口返回 HTTP 200，但未获取到账号数据', 'missing_profile_data')
            return _http_result(response.status_code, '用户接口')

        except Exception as e:
            result = _exception_result(e, '用户接口')
            logger.debug("TikTok user API failed: %s", result['error_code'])
            return result

    async def _try_oembed_api(self, client: httpx.AsyncClient, username: str) -> Dict[str, Any]:
        """从 TikTok 主页解析用户信息（备用路径）。"""
        try:
            url = f"https://www.tiktok.com/@{username}"
            response = await self._get_with_retry(client, url, self.headers)
            if is_verification_page(response):
                return _failure(VERIFICATION_REQUIRED, 'verification_required')

            if response.status_code == 200:
                # 尝试从页面中提取 __UNIVERSAL_DATA_FOR_REHYDRATION__
                content = response.text
                import json
                pattern = r'<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__"[^>]*>(.*?)</script>'
                match = re.search(pattern, content, re.DOTALL)
                if match:
                    try:
                        page_data = json.loads(match.group(1))
                        # 尝试从页面数据中提取用户信息
                        user_detail = (
                            page_data
                            .get('__DEFAULT_SCOPE__', {})
                            .get('webapp.user-detail', {})
                            .get('userInfo', {})
                        )
                        user = user_detail.get('user', {})
                        stats = user_detail.get('stats', {})
                        detail = page_data.get('__DEFAULT_SCOPE__', {}).get('webapp.user-detail', {})
                        if not user.get('id') and is_account_not_found_message(detail.get('statusMsg')):
                            return _failure(ACCOUNT_NOT_FOUND, 'account_not_found')
                        if user.get('id'):
                            create_time = user.get('createTime')
                            account_created_at = None
                            if create_time:
                                try:
                                    account_created_at = datetime.utcfromtimestamp(int(create_time))
                                except (TypeError, ValueError, OSError, OverflowError):
                                    pass
                            return {
                                'success': True,
                                'data': {
                                    'tiktok_id': user.get('id'),
                                    'sec_uid': user.get('secUid'),
                                    'nickname': user.get('nickname'),
                                    'avatar_url': user.get('avatarMedium') or user.get('avatarLarger'),
                                    'bio': user.get('signature'),
                                    **({'follower_count': stats['followerCount']}
                                       if isinstance(stats.get('followerCount'), int)
                                       and not isinstance(stats['followerCount'], bool)
                                       and stats['followerCount'] >= 0 else {}),
                                    'following_count': stats.get('followingCount', 0),
                                    'like_count': stats.get('heartCount', 0),
                                    'video_count': stats.get('videoCount', 0),
                                    'region': user.get('region'),
                                    'account_created_at': account_created_at,
                                },
                                'error': None
                            }
                    except (json.JSONDecodeError, KeyError, TypeError, AttributeError):
                        pass

            visible_text = html.unescape(re.sub(r'<script\b[^>]*>.*?</script>|<style\b[^>]*>.*?</style>', '', response.text, flags=re.S | re.I))
            visible_text = re.sub(r'<[^>]+>', ' ', visible_text)
            visible_text = ' '.join(visible_text.split())
            if response.status_code in (200, 404) and is_account_not_found_message(visible_text):
                return _failure(ACCOUNT_NOT_FOUND, 'account_not_found')
            if response.status_code == 200:
                return _failure('TikTok 主页返回 HTTP 200，但未获取到账号数据或明确的不存在提示，无法判断账号是否存在', 'missing_profile_data')
            return _http_result(response.status_code, '账号主页')

        except Exception as e:
            result = _exception_result(e, '账号主页')
            logger.debug("TikTok profile page failed: %s", result['error_code'])
            return result

    async def fetch_user_videos(self, sec_uid: str, proxy: MonitorProxy | None = None,
                                max_count: int = 20, timeout: float | None = None) -> Dict[str, Any]:
        """
        抓取用户视频列表（yt-dlp 同款 Web API 方案，支持翻页）
        流程：先访问用户详情接口获取 msToken cookie，再分页请求 item_list
        返回格式: {success: bool, data: list | None, error: str | None}
        """
        proxy_url = self._build_proxy_url(proxy)
        proxies: dict[str | httpx.URL, str | httpx.URL | httpx.Proxy | None] | None = {"all://": proxy_url} if proxy_url else None

        device_id = str(random.randint(7250000000000000000, 7325099899999994577))
        verify_fp = 'verify_' + ''.join(random.choices(string.hexdigits.lower(), k=7))

        base_headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept': 'application/json, text/plain, */*',
            'Referer': 'https://www.tiktok.com/',
        }

        all_videos: list[dict[str, Any]] = []

        def failed_page(result: Dict[str, Any]) -> Dict[str, Any]:
            if all_videos:
                # Callers must check partial before marking a collection complete.
                return {**result, 'success': True, 'data': all_videos[:max_count], 'partial': True,
                        'cause_error_code': result['error_code'], 'error_code': 'partial_result',
                        'error': f"PARTIAL_RESULT: 视频仅采集到部分分页；{result['error']}"}
            return result

        try:
            async with httpx.AsyncClient(
                proxies=proxies,
                timeout=self.timeout if timeout is None else timeout,
                follow_redirects=True,
            ) as client:
                # Step 1: 获取 msToken cookie
                warmup = await self._get_with_retry(client,
                    f'https://www.tiktok.com/api/user/detail/?uniqueId=placeholder&aid=1988&app_name=tiktok_web&device_platform=web_pc&secUid={sec_uid}',
                    base_headers,
                )
                if is_verification_page(warmup):
                    return _failure(f"视频会话初始化失败；{VERIFICATION_REQUIRED}", 'verification_required')
                if warmup.status_code != 200:
                    return _http_result(warmup.status_code, '视频会话初始化')
                cookies = {c.name: c.value for c in client.cookies.jar}
                ms_token = cookies.get('msToken', '')
                if not ms_token:
                    # Some valid TikTok sessions support an empty token; let item_list decide.
                    logger.warning("TikTok video session did not supply msToken")

                # Step 2: 分页拉取，cursor 从当前时间戳开始（newest-to-oldest）
                seen_ids = set()
                empty_result = False
                cursor = int(time.time() * 1000)

                while len(all_videos) < max_count:
                    params = {
                        'aid': '1988',
                        'app_language': 'en',
                        'app_name': 'tiktok_web',
                        'browser_language': 'en-US',
                        'browser_name': 'Mozilla',
                        'browser_online': 'true',
                        'browser_platform': 'Win32',
                        'browser_version': '5.0 (Windows)',
                        'channel': 'tiktok_web',
                        'cookie_enabled': 'true',
                        'count': '15',
                        'cursor': str(cursor),
                        'device_id': device_id,
                        'device_platform': 'web_pc',
                        'focus_state': 'true',
                        'from_page': 'user',
                        'history_len': '2',
                        'is_fullscreen': 'false',
                        'is_page_visible': 'true',
                        'language': 'en',
                        'msToken': ms_token,
                        'os': 'windows',
                        'priority_region': '',
                        'referer': '',
                        'region': 'US',
                        'screen_height': '1080',
                        'screen_width': '1920',
                        'secUid': sec_uid,
                        'type': '1',
                        'tz_name': 'UTC',
                        'verifyFp': verify_fp,
                        'webcast_language': 'en',
                    }

                    response = await self._get_with_retry(client,
                        'https://www.tiktok.com/api/creator/item_list/',
                        base_headers,
                        params=params,
                    )

                    logger.info("TikTok video API response: HTTP %s, body_len=%s", response.status_code, len(response.content))
                    if is_verification_page(response):
                        return failed_page(_failure(VERIFICATION_REQUIRED, 'verification_required'))
                    if response.status_code != 200:
                        return failed_page(_http_result(response.status_code, '视频接口'))
                    if not response.content:
                        return failed_page(_failure('视频接口返回 HTTP 200 空响应，未获得视频列表', 'invalid_response'))
                    try:
                        data = response.json()
                    except ValueError:
                        return failed_page(_failure('TikTok 视频接口返回非 JSON 内容，未获得视频列表', 'invalid_response'))
                    if not isinstance(data, dict) or not isinstance(data.get('itemList'), list):
                        return failed_page(_failure('TikTok 视频接口返回的 JSON 结构异常或缺少 itemList', 'invalid_response'))
                    item_list = data['itemList']
                    status_code = data.get('statusCode', data.get('status_code'))
                    if status_code not in (None, 0, '0'):
                        return failed_page(_failure('TikTok 视频接口未返回正常数据，可能受限或需要核实账号可见性', 'video_restricted'))

                    if not item_list:
                        empty_result = status_code in (0, "0") and isinstance(data.get('itemList'), list)
                        if not empty_result:
                            return failed_page(_failure('TikTok 视频接口返回空列表，但没有明确的正常状态', 'video_restricted'))
                        break
                    if any(not isinstance(item, dict) or not item.get('id')
                           or not isinstance(item.get('stats') or {}, dict)
                           or not isinstance(item.get('video') or {}, dict) for item in item_list):
                        return failed_page(_failure('TikTok 视频接口返回的视频字段结构异常', 'invalid_response'))

                    # 去重后加入结果
                    new_videos = [v for v in self._parse_item_list(item_list) if v['video_id'] not in seen_ids]
                    for v in new_videos:
                        seen_ids.add(v['video_id'])
                    all_videos.extend(new_videos)
                    logger.info(f"Web API fetched {len(item_list)} raw, {len(new_videos)} new (total: {len(all_videos)}, need: {max_count})")

                    has_more = data.get('hasMorePrevious', data.get('hasMore', False))

                    if len(all_videos) >= max_count:
                        break
                    if not has_more:
                        break

                    last_create_time = item_list[-1].get('createTime')
                    try:
                        new_cursor = int(float(last_create_time) * 1000)
                    except (TypeError, ValueError, OverflowError):
                        return failed_page(_failure('TikTok 视频分页缺少有效发布时间，无法继续采集', 'invalid_response'))
                    if new_cursor >= cursor:
                        return failed_page(_failure('TikTok 视频分页游标未前进，无法继续采集', 'invalid_response'))
                    cursor = new_cursor

                if all_videos:
                    video_result = all_videos[:max_count]
                    logger.info(f"Total fetched: {len(video_result)} videos")
                    return {'success': True, 'data': video_result, 'error': None}

                if empty_result:
                    return {'success': True, 'data': [], 'error': None}
                return _failure('TikTok 未返回视频列表', 'video_restricted')

        except Exception as e:
            failure_result = _exception_result(e, '视频采集')
            logger.error("TikTok video collection failed: %s", failure_result['error_code'])
            return failed_page(failure_result)

    def _parse_item_list(self, item_list: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """解析 Web API 返回的 itemList（字段名为驼峰式）"""
        videos = []
        for item in item_list:
            video_id = item.get('id')
            stats = item.get('stats') or {}
            video_info = item.get('video') or {}

            cover_url = None
            for cover_key in ('cover', 'originCover', 'dynamicCover'):
                cover_url = video_info.get(cover_key)
                if cover_url:
                    break

            videos.append({
                'video_id': video_id,
                'title': item.get('desc', ''),
                'cover_url': cover_url,
                'play_count': stats.get('playCount', 0),
                'like_count': stats.get('diggCount', 0),
                'comment_count': stats.get('commentCount', 0),
                'share_count': stats.get('shareCount', 0),
                'published_at': item.get('createTime'),
            })
        return videos

    async def test_proxy(self, proxy: MonitorProxy | None) -> Dict[str, Any]:
        """测试代理连通性，访问 TikTok 主站"""
        proxy_url = self._build_proxy_url(proxy)
        proxies: dict[str | httpx.URL, str | httpx.URL | httpx.Proxy | None] | None = {"all://": proxy_url} if proxy_url else None
        start = time.time()
        try:
            async with httpx.AsyncClient(
                proxies=proxies,
                timeout=10,
                follow_redirects=True
            ) as client:
                resp = await client.get('https://www.tiktok.com', headers=self.headers)
                elapsed = time.time() - start
                if is_verification_page(resp):
                    return {
                        'success': False,
                        'response_time': round(elapsed, 3),
                        'error': VERIFICATION_REQUIRED,
                        'error_code': 'verification_required',
                    }
                return {
                    'success': resp.status_code == 200,
                    'response_time': round(elapsed, 3),
                    'error': None if resp.status_code == 200 else f'HTTP {resp.status_code}',
                    'error_code': None if resp.status_code == 200 else _http_result(resp.status_code, '代理测试')['error_code'],
                }
        except Exception as e:
            result = _exception_result(e, '代理测试')
            return {
                'success': False,
                'response_time': round(time.time() - start, 3),
                'error': result['error'],
                'error_code': result['error_code'],
            }


scraper_service = ScraperService()
