import httpx
import asyncio
import logging
import string
import time
import random
from datetime import datetime
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class ScraperService:
    def __init__(self):
        self.timeout = 30
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://www.tiktok.com/',
        }

    def _build_proxy_url(self, proxy) -> Optional[str]:
        """构建代理URL字符串"""
        if not proxy:
            return None
        auth = f"{proxy.username}:{proxy.password}@" if proxy.username else ""
        return f"{proxy.proxy_type}://{auth}{proxy.host}:{proxy.port}"

    async def fetch_user_info(self, username: str, proxy=None) -> Dict[str, Any]:
        """
        抓取TikTok用户信息。
        返回格式: {success: bool, data: dict | None, error: str | None}
        """
        proxy_url = self._build_proxy_url(proxy)
        proxies = {"all://": proxy_url} if proxy_url else None

        try:
            async with httpx.AsyncClient(
                proxies=proxies,
                timeout=self.timeout,
                follow_redirects=True
            ) as client:
                # 尝试 TikTok web API (非官方)
                result = await self._try_web_api(client, username)
                if result['success']:
                    return result

                # 备用: TikTok oEmbed API（仅能获取基础信息）
                result = await self._try_oembed_api(client, username)
                if result['success']:
                    return result

                return {'success': False, 'data': None, 'error': 'All API endpoints failed'}

        except httpx.ProxyError as e:
            logger.error(f"Proxy error for {username}: {e}")
            return {'success': False, 'data': None, 'error': f'Proxy error: {str(e)[:200]}'}
        except httpx.TimeoutException as e:
            logger.error(f"Timeout for {username}: {e}")
            return {'success': False, 'data': None, 'error': f'Timeout: {str(e)[:200]}'}
        except Exception as e:
            logger.error(f"Scrape error for {username}: {e}")
            return {'success': False, 'data': None, 'error': str(e)[:200]}

    async def _try_web_api(self, client: httpx.AsyncClient, username: str) -> Dict[str, Any]:
        """尝试 TikTok 非官方 web API"""
        try:
            url = f"https://www.tiktok.com/api/user/detail/?uniqueId={username}&aid=1988&app_language=en&app_name=tiktok_web&device_platform=web_pc"
            response = await client.get(url, headers=self.headers)

            if response.status_code == 200:
                data = response.json()
                user_info = data.get('userInfo', {})
                user = user_info.get('user', {})
                stats = user_info.get('stats', {})

                if user.get('id'):
                    # 解析注册时间（Unix 时间戳）
                    create_time = user.get('createTime')
                    account_created_at = None
                    if create_time:
                        try:
                            account_created_at = datetime.utcfromtimestamp(int(create_time))
                        except (ValueError, OSError):
                            pass
                    return {
                        'success': True,
                        'data': {
                            'tiktok_id': user.get('id'),
                            'sec_uid': user.get('secUid'),
                            'nickname': user.get('nickname'),
                            'avatar_url': user.get('avatarMedium') or user.get('avatarLarger'),
                            'bio': user.get('signature'),
                            'follower_count': stats.get('followerCount', 0),
                            'following_count': stats.get('followingCount', 0),
                            'like_count': stats.get('heartCount', 0),
                            'video_count': stats.get('videoCount', 0),
                            'region': user.get('region'),
                            'account_created_at': account_created_at,
                        },
                        'error': None
                    }

            return {'success': False, 'data': None, 'error': f'Web API HTTP {response.status_code}'}

        except Exception as e:
            logger.debug(f"Web API failed for {username}: {e}")
            return {'success': False, 'data': None, 'error': str(e)[:200]}

    async def _try_oembed_api(self, client: httpx.AsyncClient, username: str) -> Dict[str, Any]:
        """尝试 TikTok oEmbed API（备用，数据有限）"""
        try:
            url = f"https://www.tiktok.com/@{username}"
            response = await client.get(url, headers=self.headers)

            if response.status_code == 200:
                # 尝试从页面中提取 __UNIVERSAL_DATA_FOR_REHYDRATION__
                content = response.text
                import json
                import re
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
                        if user.get('id'):
                            create_time = user.get('createTime')
                            account_created_at = None
                            if create_time:
                                try:
                                    account_created_at = datetime.utcfromtimestamp(int(create_time))
                                except (ValueError, OSError):
                                    pass
                            return {
                                'success': True,
                                'data': {
                                    'tiktok_id': user.get('id'),
                                    'sec_uid': user.get('secUid'),
                                    'nickname': user.get('nickname'),
                                    'avatar_url': user.get('avatarMedium') or user.get('avatarLarger'),
                                    'bio': user.get('signature'),
                                    'follower_count': stats.get('followerCount', 0),
                                    'following_count': stats.get('followingCount', 0),
                                    'like_count': stats.get('heartCount', 0),
                                    'video_count': stats.get('videoCount', 0),
                                    'region': user.get('region'),
                                    'account_created_at': account_created_at,
                                },
                                'error': None
                            }
                    except (json.JSONDecodeError, KeyError):
                        pass

            return {'success': False, 'data': None, 'error': f'oEmbed HTTP {response.status_code}'}

        except Exception as e:
            logger.debug(f"oEmbed API failed for {username}: {e}")
            return {'success': False, 'data': None, 'error': str(e)[:200]}

    async def fetch_user_videos(self, sec_uid: str, proxy=None, max_count: int = 20) -> Dict[str, Any]:
        """
        抓取用户视频列表（yt-dlp 同款 Web API 方案，支持翻页）
        流程：先访问用户详情接口获取 msToken cookie，再分页请求 item_list
        返回格式: {success: bool, data: list | None, error: str | None}
        """
        proxy_url = self._build_proxy_url(proxy)
        proxies = {"all://": proxy_url} if proxy_url else None

        device_id = str(random.randint(7250000000000000000, 7325099899999994577))
        verify_fp = 'verify_' + ''.join(random.choices(string.hexdigits.lower(), k=7))

        base_headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept': 'application/json, text/plain, */*',
            'Referer': 'https://www.tiktok.com/',
        }

        try:
            async with httpx.AsyncClient(
                proxies=proxies,
                timeout=self.timeout,
                follow_redirects=True,
            ) as client:
                # Step 1: 获取 msToken cookie
                await client.get(
                    f'https://www.tiktok.com/api/user/detail/?uniqueId=placeholder&aid=1988&app_name=tiktok_web&device_platform=web_pc&secUid={sec_uid}',
                    headers=base_headers,
                )
                cookies = {c.name: c.value for c in client.cookies.jar}
                ms_token = cookies.get('msToken', '')

                # Step 2: 分页拉取，cursor 从当前时间戳开始（newest-to-oldest）
                all_videos = []
                seen_ids = set()
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

                    response = await client.get(
                        'https://www.tiktok.com/api/creator/item_list/',
                        params=params,
                        headers=base_headers,
                    )

                    logger.info(f"Web API response: {response.status_code}, body_len: {len(response.content)}, cursor={cursor}")

                    if response.status_code != 200 or not response.content:
                        preview = response.text[:200] if response.content else '(empty)'
                        logger.warning(f"Web API non-200: {response.status_code}, body: {preview}")
                        if not all_videos:
                            return {'success': False, 'data': None, 'error': f'HTTP {response.status_code}'}
                        break

                    data = response.json()
                    item_list = data.get('itemList', [])

                    if not item_list:
                        status_code = data.get('statusCode', data.get('status_code', 0))
                        logger.warning(f"Web API empty itemList, statusCode={status_code}")
                        break

                    # 去重后加入结果
                    new_videos = [v for v in self._parse_item_list(item_list) if v['video_id'] not in seen_ids]
                    for v in new_videos:
                        seen_ids.add(v['video_id'])
                    all_videos.extend(new_videos)
                    logger.info(f"Web API fetched {len(item_list)} raw, {len(new_videos)} new (total: {len(all_videos)}, need: {max_count})")

                    has_more = data.get('hasMorePrevious', data.get('hasMore', False))
                    logger.info(f"hasMorePrevious={has_more}")

                    if len(all_videos) >= max_count:
                        break
                    if not has_more and len(item_list) < 15:
                        break  # 真的到底了

                    last_create_time = item_list[-1].get('createTime')
                    if not last_create_time:
                        break
                    new_cursor = int(last_create_time * 1000)
                    if new_cursor >= cursor:
                        break  # 防止死循环
                    cursor = new_cursor

                if all_videos:
                    result = all_videos[:max_count]
                    logger.info(f"Total fetched: {len(result)} videos")
                    return {'success': True, 'data': result, 'error': None}

                return {'success': False, 'data': None, 'error': 'No videos returned'}

        except Exception as e:
            logger.error(f"fetch_user_videos error for sec_uid={sec_uid}: {e}")
            return {'success': False, 'data': None, 'error': str(e)[:200]}

    def _parse_item_list(self, item_list: list) -> list:
        """解析 Web API 返回的 itemList（字段名为驼峰式）"""
        videos = []
        for item in item_list:
            video_id = item.get('id')
            stats = item.get('stats', {})
            video_info = item.get('video', {})

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

    async def test_proxy(self, proxy) -> Dict[str, Any]:
        """测试代理连通性，访问 TikTok 主站"""
        proxy_url = self._build_proxy_url(proxy)
        proxies = {"all://": proxy_url} if proxy_url else None
        start = time.time()
        try:
            async with httpx.AsyncClient(
                proxies=proxies,
                timeout=10,
                follow_redirects=True
            ) as client:
                resp = await client.get('https://www.tiktok.com', headers=self.headers)
                elapsed = time.time() - start
                return {
                    'success': resp.status_code < 500,
                    'response_time': round(elapsed, 3),
                    'error': None
                }
        except Exception as e:
            return {
                'success': False,
                'response_time': round(time.time() - start, 3),
                'error': str(e)[:100]
            }


scraper_service = ScraperService()
