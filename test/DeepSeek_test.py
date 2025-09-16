import os
from openai import OpenAI

client = OpenAI(
    # 若没有配置环境变量，请用阿里云百炼API Key将下行替换为：api_key="sk-xxx",
    api_key="sk-7fbfac05d6314d779d70da5702583576",
    base_url="https://api.deepseek.com"
)

completion = client.chat.completions.create(
    model="deepseek-v3.1",  # 此处以 deepseek-v3.1 为例，可按需更换模型名称。
    messages=[
        {'role': 'user', 'content': '9.9和9.11谁大'}
    ]
)

# 判断是否有reasoning_content
# deepseek-v3.1默认不输出思考过程。如需输出思考过程，请参见流式输出的代码。
if hasattr(completion.choices[0].message, 'reasoning_content'):
    print("思考过程：")
    print(completion.choices[0].message.reasoning_content)

print("最终答案：")
print(completion.choices[0].message.content)