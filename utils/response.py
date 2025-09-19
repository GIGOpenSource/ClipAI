# utils/response.py
from rest_framework.response import Response

def success_response(data=None, message="成功", code=200):
    """统一成功响应格式"""
    response_data = {
        'code': code,
        'message': message,
        'data': data,
        'success': True
    }
    return Response(response_data, status=code if code < 400 else 200)

def error_response(message="失败", code=400, data=None):
    """统一错误响应格式"""
    response_data = {
        'code': code,
        'message': message,
        'data': data,
        'success': False
    }
    return Response(response_data, status=code)

# 特定错误类型的快捷函数
def bad_request(message="请求参数错误", data=None):
    return error_response(message, 400, data)

def unauthorized(message="未授权访问"):
    return error_response(message, 401)

def forbidden(message="权限不足"):
    return error_response(message, 403)

def not_found(message="资源不存在"):
    return error_response(message, 404)

def server_error(message="服务器内部错误"):
    return error_response(message, 500)
