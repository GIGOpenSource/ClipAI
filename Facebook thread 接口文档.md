# Threads API 操作全量说明（含参数对照表+Python代码）
## 核心结论
本文档整合Thread API发帖、回复、提及操作的详细说明、完整参数对照表、Python代码示例及问题排查，适配开发者实际开发需求，可直接作为接口调用参考手册。

## 一、前置准备
### 1.1 开发者环境要求
1. 注册Facebook开发者账号，完成身份验证后创建应用，提交应用审核（需说明Thread API使用场景）。
2. 申请接口权限，必选`threads_basic`（基础查询权限）、`threads_manage_posts`（发布/回复操作权限）。
3. 获取`access_token`：通过应用后台“工具-访问令牌”生成，或调用OAuth2.0接口获取用户授权令牌，默认有效期60天，可延长至90天。
### 1.2 依赖工具
- 编程语言：Python 3.7及以上版本。
- 依赖库：安装`requests`库，执行命令`pip install requests`即可。

## 二、核心接口参数总表
### 2.1 发帖接口（POST /me/threads）
| 参数名               | 类型       | 是否必填 | 取值范围/可选值                          | 限制条件                                                                 | 备注说明                                                                 |
|----------------------|------------|----------|------------------------------------------|--------------------------------------------------------------------------|--------------------------------------------------------------------------|
| content              | string     | 是       | 任意文本                                 | 最大长度500字符，支持`\n`换行、#话题标签、@用户名占位符                  | 文本为空或超长篇会返回400错误                                             |
| mentions             | array      | 否       | 数字用户ID列表（如["123", "456"]）       | 最多10个用户ID，需提前校验有效性                                        | 与文本中@用户名一一对应，否则提及不生效                                   |
| visibility           | string     | 否       | PUBLIC（默认）、FOLLOWER_ONLY            | 仅对当前账号发布的帖子生效                                              | FOLLOWER_ONLY仅自己的关注者可见                                          |
| is_pin               | boolean    | 否       | true、false（默认）                      | 仅支持置顶自己发布的帖子，最多同时置顶1条                                | 置顶后原置顶帖子会自动取消                                               |
| media_ids            | array      | 否       | 媒体文件ID列表（如["media_123", "media_456"]） | 最多添加4个媒体文件，支持图片（JPG/PNG）、视频（MP4）                    | 需先通过`/me/media`接口上传媒体获取ID，视频最大500MB、时长≤120秒          |
| caption              | string     | 否       | 任意文本                                 | 仅当传入media_ids时生效，作为媒体的补充说明，最大长度100字符             | 与content字段并行显示，content优先展示                                   |
| access_token         | string     | 是       | 开发者/用户授权令牌                      | 必须包含`threads_manage_posts`权限，令牌过期会返回401错误                | 建议定期通过OAuth2.0刷新令牌                                             |

### 2.2 回复接口（POST /{parent_id}/replies）
| 参数名               | 类型       | 是否必填 | 取值范围/可选值                          | 限制条件                                                                 | 备注说明                                                                 |
|----------------------|------------|----------|------------------------------------------|--------------------------------------------------------------------------|--------------------------------------------------------------------------|
| content              | string     | 是       | 任意文本                                 | 最大长度300字符，支持`\n`换行、#话题标签、@用户名占位符                  | 比主帖字数限制更严格，超长篇返回400错误                                   |
| mentions             | array      | 否       | 数字用户ID列表（如["123", "456"]）       | 最多5个用户ID，需提前校验有效性                                        | 仅可提及主帖作者或其他回复者                                             |
| parent_id            | string     | 是       | 帖子ID（thread_xxx）或回复ID（reply_xxx） | 需确认parent_id对应的内容存在，否则返回404错误                           | 嵌套回复需传入上一条回复的ID（reply_xxx）                                |
| access_token         | string     | 是       | 开发者/用户授权令牌                      | 必须包含`threads_manage_posts`权限，无权限返回403错误                    | 回复他人帖子需确保对方账号未设置“仅好友可回复”                            |

### 2.3 用户信息查询接口（GET /{user_id}）
| 参数名               | 类型       | 是否必填 | 取值范围/可选值                          | 限制条件                                                                 | 备注说明                                                                 |
|----------------------|------------|----------|------------------------------------------|--------------------------------------------------------------------------|--------------------------------------------------------------------------|
| fields               | string     | 否       | id、username、threads_count、followers_count | 多个字段用逗号分隔（如“id,username”）                                    | 未指定字段时默认仅返回id                                                 |
| access_token         | string     | 是       | 开发者/用户授权令牌                      | 仅需`threads_basic`基础权限，查询他人信息需对方账号公开可见              | 查询自己账号信息无额外限制，查询他人可能返回部分字段隐藏                   |

## 三、参数使用约束总览
1. **权限关联约束**：发布/回复/删除操作需`threads_manage_posts`权限，仅查询操作需`threads_basic`权限。
2. **频率限制约束**：单令牌每分钟最多调用60次接口，单日发布/回复总量不超过1000条。
3. **格式约束**：布尔类型参数需传入小写字符串（"true"/"false"），数组类型参数需转为逗号分隔字符串。

## 四、发帖操作（含高级功能）
### 4.1 功能描述
支持发布纯文本、含提及用户、带媒体文件及话题标签的Thread帖子，可设置可见性和置顶状态。
### 4.2 Python代码示例（含错误处理）
```python
import requests
from requests.exceptions import RequestException

# 全局配置
ACCESS_TOKEN = "YOUR_ACCESS_TOKEN"  # 替换为你的令牌
API_BASE_URL = "https://graph.threads.net/v1.0"

def create_thread_post(
    content: str,
    mention_ids: list = None,
    visibility: str = "PUBLIC",
    is_pin: bool = False,
    media_ids: list = None,
    caption: str = None
) -> dict:
    """
    发布Thread帖子
    :param content: 帖子文本内容
    :param mention_ids: 提及用户ID列表（可选）
    :param visibility: 可见性（PUBLIC/FOLLOWER_ONLY，可选）
    :param is_pin: 是否置顶（可选）
    :param media_ids: 媒体文件ID列表（可选）
    :param caption: 媒体补充说明（可选）
    :return: 接口响应结果（字典）
    """
    url = f"{API_BASE_URL}/me/threads"
    # 构造请求参数
    params = {
        "content": content,
        "visibility": visibility,
        "is_pin": str(is_pin).lower(),
        "access_token": ACCESS_TOKEN
    }
    # 补充可选参数
    if mention_ids and isinstance(mention_ids, list):
        params["mentions"] = ",".join(mention_ids)
    if media_ids and isinstance(media_ids, list):
        params["media_ids"] = ",".join(media_ids)
        if caption:
            params["caption"] = caption[:100]  # 截取前100字符，避免超限
    
    try:
        response = requests.post(url, params=params, timeout=10)
        response.raise_for_status()
        return {
            "success": True,
            "data": response.json(),
            "post_id": response.json().get("id")
        }
    except RequestException as e:
        error_msg = str(e)
        if hasattr(e, "response") and e.response is not None:
            error_msg = f"{error_msg} | 接口响应：{e.response.text}"
        return {
            "success": False,
            "error": error_msg
        }

# 调用示例：发布含提及、媒体和话题的帖子
if __name__ == "__main__":
    post_content = "测试Thread高级发帖功能！\n@好友1 @好友2 一起讨论#ThreadAPI #Python开发"
    target_mention_ids = ["123456789", "987654321"]  # 替换为实际用户ID
    target_media_ids = ["media_111", "media_222"]  # 替换为实际媒体ID
    result = create_thread_post(
        content=post_content,
        mention_ids=target_mention_ids,
        visibility="PUBLIC",
        is_pin=False,
        media_ids=target_media_ids,
        caption="这是测试媒体的补充说明"
    )
    if result["success"]:
        print(f"发帖成功！帖子ID：{result['post_id']}")
    else:
        print(f"发帖失败：{result['error']}")
```

## 五、回复操作（含嵌套回复）
### 5.1 功能描述
支持针对帖子或已有回复发送嵌套回复，可提及用户和添加话题标签。
### 5.2 Python代码示例
```python
def reply_to_thread(parent_id: str, content: str, mention_ids: list = None) -> dict:
    """
    回复Thread帖子/回复
    :param parent_id: 目标帖子/回复的ID
    :param content: 回复文本内容
    :param mention_ids: 提及用户ID列表（可选）
    :return: 接口响应结果（字典）
    """
    url = f"{API_BASE_URL}/{parent_id}/replies"
    params = {
        "content": content,
        "access_token": ACCESS_TOKEN
    }
    if mention_ids and isinstance(mention_ids, list):
        params["mentions"] = ",".join(mention_ids[:5])  # 限制最多5个提及用户
    
    try:
        response = requests.post(url, params=params, timeout=10)
        response.raise_for_status()
        return {
            "success": True,
            "data": response.json(),
            "reply_id": response.json().get("id")
        }
    except RequestException as e:
        error_msg = str(e)
        if hasattr(e, "response") and e.response is not None:
            error_msg = f"{error_msg} | 接口响应：{e.response.text}"
        return {
            "success": False,
            "error": error_msg
        }

# 调用示例：主帖→一级回复→嵌套回复
if __name__ == "__main__":
    # 1. 发布主帖
    main_post = create_thread_post(content="这是一条主帖，欢迎回复！")
    if not main_post["success"]:
        print("主帖发布失败")
        exit()
    main_post_id = main_post["post_id"]
    
    # 2. 一级回复
    reply1 = reply_to_thread(main_post_id, "第一条回复，@主帖作者", ["123456789"])
    if reply1["success"]:
        reply1_id = reply1["reply_id"]
        # 3. 嵌套回复
        reply2 = reply_to_thread(reply1_id, "嵌套回复第一条回复")
        print(f"嵌套回复成功，ID：{reply2['reply_id']}" if reply2["success"] else f"嵌套回复失败：{reply2['error']}")
```

## 六、提及操作与用户ID校验
### 6.1 提及功能细节
文本中用`@用户名`显示，API参数需传入用户数字ID，可通过Graph API`/用户名?fields=id&access_token=令牌`获取用户ID。
### 6.2 用户ID校验Python函数
```python
def check_user_id_validity(user_id: str) -> bool:
    """
    校验用户ID是否有效
    :param user_id: 待校验的用户ID
    :return: 有效返回True，无效返回False
    """
    url = f"{API_BASE_URL}/{user_id}"
    params = {
        "fields": "id",
        "access_token": ACCESS_TOKEN
    }
    try:
        response = requests.get(url, params=params, timeout=5)
        return response.status_code == 200
    except RequestException:
        return False

# 调用示例
if __name__ == "__main__":
    user_id = "123456789"
    print(f"用户ID {user_id} 有效：{check_user_id_validity(user_id)}")
```

## 七、常见问题与排查
1. **401 Unauthorized**：令牌过期或权限不足，重新生成令牌并确认权限已申请。
2. **403 Forbidden**：应用未通过审核，或操作超出权限范围（如置顶他人帖子）。
3. **429 Too Many Requests**：接口调用超限，暂停1分钟后重试。
4. **400 Bad Request**：参数错误（如字符超限、无效ID），参考参数对照表校验输入。
5. **500 Internal Server Error**：Facebook服务器异常，记录参数后重试。

## 八、接口响应格式说明
### 8.1 成功响应示例（发帖）
```json
{
  "id": "thread_1234567890abcdef",
  "created_time": "2024-05-20T10:30:00+0000",
  "content": "测试帖子内容",
  "visibility": "PUBLIC",
  "media": [{"id": "media_111", "type": "image"}]
}
```
### 8.2 失败响应示例（无效参数）
```json
{
  "error": {
    "message": "Invalid user ID",
    "type": "OAuthException",
    "code": 400,
    "fbtrace_id": "abc123xyz"
  }
}
```
## 九、 Thread API 接口调用测试脚本(Python)
```python
import requests
from requests.exceptions import RequestException
import time

# ==================== 测试配置（用户需替换以下参数）====================
ACCESS_TOKEN = "YOUR_ACCESS_TOKEN"  # 替换为你的有效令牌
TEST_USER_IDS = ["VALID_USER_ID_1", "VALID_USER_ID_2"]  # 替换为2个有效用户ID
INVALID_USER_ID = "INVALID_USER_ID_999"  # 无效用户ID（用于异常测试）
TEST_MEDIA_IDS = ["VALID_MEDIA_ID_1"]  # 可选，替换为有效媒体ID（无则留空列表）
API_BASE_URL = "https://graph.threads.net/v1.0"

# ==================== 全局工具函数 ====================
def print_separator(title: str):
    """打印测试分隔符，区分不同测试模块"""
    print(f"\n{'='*50} {title} {'='*50}")

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
```
### 脚本使用说明
1. **参数配置**：替换脚本顶部`测试配置`区域的`ACCESS_TOKEN`、`TEST_USER_IDS`等参数（需用自己的有效信息）。
2. **依赖安装**：确保已安装`requests`库，执行`pip install requests`即可。
3. **运行方式**：直接运行脚本，控制台会输出每个测试用例的结果（成功/失败）及详细日志。
4. **测试场景覆盖**：包含有效/无效用户ID校验、正常/超限字符发帖、主帖回复/嵌套回复等核心场景。