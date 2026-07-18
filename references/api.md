# RIRS API 参考（逆向前端 2026-07）

## 入口

| 角色 | Base |
|------|------|
| Web SPA | http://202.114.114.19:8001 |
| REST API | http://202.114.114.19:8002 |
| code-server | https://202.114.114.19:8003/code-server/{podName}/?folder=/data/user |

认证：HTTP Header `satoken: <token>`（登录后也可 Set-Cookie）。

统一响应：`{"code":200,"msg":"...","data":...}`；401 未登录，402 业务拒绝，500 服务器错误。

## Auth

### POST /auth/login

```json
{"username":"crz","password":"..."}
```

返回 `data.tokenInfo.tokenValue` 与 `data.user`。

### GET /system/user/self

当前用户。

## 镜像 /k8s/image

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /k8s/image/user?page&size | 用户可见镜像 |
| GET | /k8s/image/all?page&size | 全部镜像 |
| GET | /k8s/image/{id} | 详情 |
| POST | /k8s/image/{containerId} | 从容器保存镜像 |
| DELETE | /k8s/image/{id} | 删除 |

镜像字段：`id,name,tag,description,access,supportCodeServer,supportWebTop`。

常用公共镜像：

| id | ref |
|----|-----|
| 1 | pytorch:1.13_11.6_8 |
| 2 | ubuntu_cuda:20.04_11.7.0 |
| 3 | pytorch:1.11.0_11.3_8 |
| 8 | pytorch:1.12.1_11.3_8 |
| 6 | novnc-code_server:debian-xfce |
| 7 | novnc:ubuntu20-xfce |

## 容器 /k8s/container

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /k8s/container/user?page&size | 我的容器 |
| GET | /k8s/container/user/checkExist?name= | 名称是否存在 |
| POST | /k8s/container/ | 新建 |
| DELETE | /k8s/container/{id} | 删除 |
| GET | /k8s/container/code-server/{id} | 返回 IDE URL 字符串 |
| GET | /k8s/container/web-top/{id} | noVNC URL |
| GET | /k8s/container/all | 管理员 |
| GET | /k8s/container/filter/audit | 待审核 |
| PUT | /k8s/container/audit/{id} | `{"pass":true/false}` |

### 创建 body

```json
{
  "name": "exp-demo",
  "imageId": "1",
  "cpuRequests": 2,
  "memoryRequests": 4,
  "gpuRequests": 1
}
```

默认值与前端一致：cpu=2, memory=4Gi, gpu=1。gpu>1 可能触发审核。

容器名正则：`^(([A-Za-z0-9][-A-Za-z0-9_.]*)?[A-Za-z0-9])$`

### 状态

`status` 常见：`RUNNING` 等。仅 RUNNING 可打开 code-server。

工作目录惯例：`/data/user`。

## code-server 操作

无官方简单文件 REST。本 skill 用 Playwright 打开 IDE，通过终端执行命令；文件经 base64/tar 上传。

健康检查：`GET https://.../code-server/{pod}/healthz` → `{"status":"alive",...}`（忽略证书错误）。
