# Windows 安装器构建说明

安装器脚本使用 Inno Setup 7、`wizard.bmp` 和 `wizard-small.bmp`。这两个图片使用项目的三视图立绘制作；可在 Windows 上安装 Pillow 后运行 `python installer/生成安装界面.py` 重新生成。

首先使用 PyInstaller 的目录模式生成程序，确保 `sprites/` 打入内部资源目录，`imageio_ffmpeg` 可执行文件被收集；将项目的 `anim/` 复制到程序可执行文件旁，附带 LICENSE、溯源与致谢和使用说明。准备好的目录应包含 `大肥鱼桌宠.exe`、`_internal/` 和 `anim/`，不应包含个人配置、聊天记录、Key 或浏览器数据。

标准版仅需复制 `anim/` 中的文件，不要把 `anim/hd/` 打入安装器。将 `FISH_INSTALL_SOURCE` 指向上述目录，将 `FISH_INSTALL_OUTPUT` 指向输出目录，然后使用 Inno Setup 编译 `installer/大肥鱼桌宠.iss`。安装器为当前用户安装，支持自选目录、可选桌面快捷方式和联网安装高清动画。

高清 ZIP 过大，不适合通过 GitHub 浏览器一次上传，发布时应拆成 4 个小于 200 MiB 的分卷。安装脚本逐卷下载并校验 SHA-256，合并成原 ZIP，再由 Inno Setup 在安装向导中解压到 `{app}`。重新生成扩展包时，必须重新分卷，并同步更新下载链接、分卷大小和哈希，再重新编译。

用户配置位于用户配置目录，卸载安装文件时保留。

本安装器包含的角色及动画素材遵循原作者非商业使用要求，详见项目 README 与溯源说明。

发布素材的再生成方式：先把项目 `anim/hd/` 与清单打成 ZIP，然后运行：

```powershell
python installer/准备高清分卷.py 高清动画.zip 输出目录
```

脚本会输出每个上传分卷的字节数和 SHA-256，供更新 Inno Setup 下载清单并核验上传资产。
