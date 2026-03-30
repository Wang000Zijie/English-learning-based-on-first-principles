from __future__ import annotations

from core.api_client import APIClient, APIClientError


def main() -> None:
    client = APIClient("config.yaml")
    prompt = input("请输入测试问题（回车使用默认）: ").strip() or "请用一句话介绍英语词汇学习。"

    try:
        answer = client.ask(prompt)
    except APIClientError as exc:
        print(f"API 调用失败: {exc}")
        return

    print("\n模型回复:\n")
    print(answer)


if __name__ == "__main__":
    main()
