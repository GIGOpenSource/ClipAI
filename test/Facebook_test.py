#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""
@Project ：ClipAI 
@File    ：Facebook_test.py
@Author  ：LYP
@Date    ：2025/10/21 17:20 
@description :
"""
import requests
from requests.exceptions import RequestException
import time

# ==================== 测试配置（用户需替换以下参数）====================
ACCESS_TOKEN = "YOUR_ACCESS_TOKEN"  # 替换为你的有效令牌
TEST_USER_IDS = ["VALID_USER_ID_1", "VALID_USER_ID_2"]  # 替换为2个有效用户ID
INVALID_USER_ID = "INVALID_USER_ID_999"  # 无效用户ID（用于异常测试）
TEST_MEDIA_IDS = []  # 可选，替换为有效媒体ID（无则留空列表）
API_BASE_URL = "https://graph.threads.net/v1.0"


# ==================== 全局工具函数 ====================
def print_separator(title: str):
    """打印测试分隔符，区分不同测试模块"""
    print(f"\n{'=' * 50} {title} {'=' * 50}")


def log_result(test_name: str, success: bool, message: str = ""):
    """记录测试结果，格式化输出"""
    status = "✅ 成功" if success else "❌ 失败"
    print(f"[{test_name}] {status}")
    if message:
        print(f"  详情：{message}")


# ==================== 测试用例函数 ====================
class ThreadAPITester:
    def __init__(self, access_token: str):
        self.access_token = access_token
        self.test_post_id = None  # 存储测试发帖的ID，用于后续回复测试
        self.test_reply_id = None  # 存储测试回复的ID，用于嵌套回复测试

    def test_user_id_validity(self):
        """测试用户ID校验接口（正常+异常场景）"""
        print_separator("测试：用户ID校验接口")

        # 用例1：校验有效用户ID
        valid_id = TEST_USER_IDS[0]
        try:
            url = f"{API_BASE_URL}/{valid_id}"
            params = {"fields": "id", "access_token": self.access_token}
            response = requests.get(url, params=params, timeout=5)
            success = response.status_code == 200
            log_result(
                test_name=f"校验有效ID [{valid_id}]",
                success=success,
                message=f"响应码：{response.status_code} | 响应内容：{response.text[:100]}"
            )
        except RequestException as e:
            log_result(
                test_name=f"校验有效ID [{valid_id}]",
                success=False,
                message=f"异常：{str(e)}"
            )

        # 用例2：校验无效用户ID
        try:
            url = f"{API_BASE_URL}/{INVALID_USER_ID}"
            params = {"fields": "id", "access_token": self.access_token}
            response = requests.get(url, params=params, timeout=5)
            success = response.status_code != 200  # 预期返回非200
            log_result(
                test_name=f"校验无效ID [{INVALID_USER_ID}]",
                success=success,
                message=f"响应码：{response.status_code} | 响应内容：{response.text[:100]}"
            )
        except RequestException as e:
            log_result(
                test_name=f"校验无效ID [{INVALID_USER_ID}]",
                success=False,
                message=f"异常：{str(e)}"
            )

    def test_create_post(self):
        """测试发帖接口（正常+异常场景）"""
        print_separator("测试：发帖接口")

        # 用例1：发布正常文本帖子（含提及）
        normal_content = "Thread API 测试：正常发帖（含提及）\n@测试用户 #API测试"
        try:
            url = f"{API_BASE_URL}/me/threads"
            params = {
                "content": normal_content,
                "mentions": ",".join(TEST_USER_IDS[:2]),  # 最多2个有效ID
                "visibility": "PUBLIC",
                "is_pin": "false",
                "access_token": self.access_token
            }
            # 若有测试媒体ID，添加媒体参数
            if TEST_MEDIA_IDS:
                params["media_ids"] = ",".join(TEST_MEDIA_IDS[:1])
                params["caption"] = "测试媒体补充说明"

            response = requests.post(url, params=params, timeout=10)
            response_data = response.json()
            success = response.status_code == 200 and "id" in response_data
            if success:
                self.test_post_id = response_data["id"]  # 保存帖子ID供后续测试
            log_result(
                test_name="发布正常文本（含提及/媒体）",
                success=success,
                message=f"响应码：{response.status_code} | 帖子ID：{self.test_post_id or '无'}"
            )
        except RequestException as e:
            log_result(
                test_name="发布正常文本（含提及/媒体）",
                success=False,
                message=f"异常：{str(e)}"
            )

        # 用例2：发布超限字符帖子（预期失败）
        long_content = "a" * 600  # 超过500字符限制
        try:
            url = f"{API_BASE_URL}/me/threads"
            params = {
                "content": long_content,
                "access_token": self.access_token
            }
            response = requests.post(url, params=params, timeout=10)
            success = response.status_code != 200  # 预期失败
            log_result(
                test_name="发布超限字符帖子（500+字符）",
                success=success,
                message=f"响应码：{response.status_code} | 错误信息：{response.text[:100]}"
            )
        except RequestException as e:
            log_result(
                test_name="发布超限字符帖子（500+字符）",
                success=False,
                message=f"异常：{str(e)}"
            )

    def test_reply_post(self):
        """测试回复接口（需先成功发布测试帖子）"""
        print_separator("测试：回复接口")
        if not self.test_post_id:
            log_result(test_name="回复接口前置检查", success=False, message="无有效测试帖子ID，跳过回复测试")
            return

        # 用例1：回复主帖（正常场景）
        reply_content = "测试：回复主帖的正常内容 @主帖作者"
        try:
            url = f"{API_BASE_URL}/{self.test_post_id}/replies"
            params = {
                "content": reply_content,
                "mentions": TEST_USER_IDS[0],  # 提及主帖作者
                "access_token": self.access_token
            }
            response = requests.post(url, params=params, timeout=10)
            response_data = response.json()
            success = response.status_code == 200 and "id" in response_data
            if success:
                self.test_reply_id = response_data["id"]  # 保存回复ID供嵌套测试
            log_result(
                test_name=f"回复主帖 [{self.test_post_id}]",
                success=success,
                message=f"响应码：{response.status_code} | 回复ID：{self.test_reply_id or '无'}"
            )
        except RequestException as e:
            log_result(
                test_name=f"回复主帖 [{self.test_post_id}]",
                success=False,
                message=f"异常：{str(e)}"
            )

        # 用例2：嵌套回复（回复上一条回复）
        if self.test_reply_id:
            nested_reply_content = "测试：嵌套回复上一条回复"
            try:
                url = f"{API_BASE_URL}/{self.test_reply_id}/replies"
                params = {
                    "content": nested_reply_content,
                    "access_token": self.access_token
                }
                response = requests.post(url, params=params, timeout=10)
                success = response.status_code == 200 and "id" in response.json()
                log_result(
                    test_name=f"嵌套回复 [{self.test_reply_id}]",
                    success=success,
                    message=f"响应码：{response.status_code}"
                )
            except RequestException as e:
                log_result(
                    test_name=f"嵌套回复 [{self.test_reply_id}]",
                    success=False,
                    message=f"异常：{str(e)}"
                )
        else:
            log_result(test_name="嵌套回复", success=False, message="无有效回复ID，跳过")

    def run_all_tests(self):
        """执行所有测试用例"""
        print("===== Thread API 接口测试脚本开始执行 =====")
        # 1. 先校验用户ID（基础接口）
        self.test_user_id_validity()
        time.sleep(1)  # 避免调用过频
        # 2. 测试发帖（核心操作）
        self.test_create_post()
        time.sleep(1)
        # 3. 测试回复（依赖发帖结果）
        self.test_reply_post()
        print("\n===== Thread API 接口测试脚本执行完毕 =====")


# ==================== 执行测试 ====================
if __name__ == "__main__":
    # 初始化测试器
    tester = ThreadAPITester(access_token=ACCESS_TOKEN)
    # 执行所有测试用例
    tester.run_all_tests()