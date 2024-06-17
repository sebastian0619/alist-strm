# alist-strm
 alist生成可播放strm视频文件

## docker部署 


```
部署前参数需要修改
必要参数
alistServerUrl  alist地址 如http://192.168.1.2:5244
alistServerToken 可在alist后台获取
alistScanPath 需要生成strm文件的目录如http://192.168.1.2:5244/阿里云分享/电影 那就填入/阿里云分享/电影
可选参数
slowMode  单线程模式，防止请求网盘太快，默认0，启用填1
encode 是否编码strm文件里面的链接  默认1启用  不启用填0
tgToken  tg机器人token，通过t.me/BotFather机器人创建bot获取token
tgUserId tg用户id，通过t.me/userinfobot机器人获取userId
isDownSub 是否下载目录里面的字幕文件 默认0不下载  下载填1
```

# 开发计划

- [x] tg机器人命令生成strm文件
- [ ] ...

# 更新记录

20240610 重构代码,增加tg机器人命令strm、strmdir
20240617 增加下载目录中字幕文件的功能

# docker CLI安装

```
docker run -d \
--name=alist-strm \
-e TZ=Asia/Shanghai \
-e alistServerUrl=http://192.168.1.2:5244 \
-e alistServerToken=xxx \
-e alistScanPath='/阿里云分享/电影' \
-e slowMode=0 \
-v /volume1/docker/alist-strm/data:/data \
jacksaoding/alist-strm:latest
```

# docker compose安装

```
version: "3"
services:
  app:
    container_name: alist-strm
    image: 'jacksaoding/alist-strm:latest'
    network_mode: "host"
    environment:
      TZ: Asia/Shanghai
      alistServerUrl: http://192.168.1.2:5244
      alistServerToken: xxx
      alistScanPath: /阿里云分享/电影
      slowMode: 0
    volumes:
      - /volume1/docker/alist-strm/data:/data
```
