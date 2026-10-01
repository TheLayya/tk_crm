"""Run an explicit third-party probe without accessing the CRM database."""
import argparse
import json
import sys

from app.services.gmail_checker_service import check_gmail_accounts, normalize_status


def main():
    parser = argparse.ArgumentParser(description="向 gmail0918.top 发送 Gmail 地址探测状态，不发送密码")
    parser.add_argument("emails", nargs="+", help="完整 Gmail 地址，单次最多 50 个")
    parser.add_argument("--consent", action="store_true", help="确认允许把邮箱地址发送给第三方")
    args = parser.parse_args()
    if not args.consent:
        parser.error("请确认第三方传输风险并指定 --consent")
    try:
        results = check_gmail_accounts(args.emails)
    except Exception:
        print("检测失败：网络异常、地址无效或第三方结果不完整；不应据此判断账号封禁。", file=sys.stderr)
        return 1
    print(json.dumps([
        {"email": result["email"], "status": normalize_status(result["status"]), "raw_status": result["status"]}
        for result in results
    ], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
