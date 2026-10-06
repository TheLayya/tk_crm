# Windows 本地打包指引

> 目的：每个阶段性功能完成后，在本机生成可安装的 Windows x64 包，并用可重复的验收流程确认能启动、数据不混入、UI 不变形、更新器可用。
> 更新日期：2026-10-06

## 1. 固定流程

开发完成后固定执行：

改版本号 → 构建运行包 → 构建安装器 → 发布审计 → 隔离安装验证 → 人工可见验收 → 记录 SHA-256 → 再决定是否提交、推送或部署。

构建与自动化夹具不应读取或上传真实业务数据库；人工启动必须显式指定临时数据目录，避免默认打开已有用户库。运行时数据不能进入 desktop/runtime。

## 2. 环境要求

从项目根目录 F:/编程相关软件/crm/tk_crm 执行。

- Windows x64。
- Python 3.12 和 backend/.venv312。
- Node.js/npm，frontend 依赖已安装。
- .NET 10 SDK；优先选择 PATH 中具备 .NET 10 SDK 的 dotnet，否则使用 %LOCALAPPDATA%/TkCRM-Dev/dotnet/dotnet.exe。只有运行时的 dotnet 不可用于构建。
- Inno Setup 6；默认使用 %LOCALAPPDATA%/Programs/Inno Setup 6/ISCC.exe。
- WebView2 Bootstrapper 下载需要网络。

检查工具：

    Test-Path .\backend\.venv312\Scripts\python.exe
    Test-Path .\frontend\package.json
    Test-Path "$env:LOCALAPPDATA\TkCRM-Dev\dotnet\dotnet.exe"
    Test-Path "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"

如果 .NET 或 Inno 不在默认位置，分别给 publish.ps1 的 Dotnet 参数和 build-installer.ps1 的 Iscc 参数传绝对路径。

注意：部分审计脚本会独立寻找默认路径的 .NET/Inno，而不继承以上参数。换机器时优先使用默认位置；否则先核对 desktop/tests 下的工具路径，不能把单独编译成功视为审计通过。

### 首次准备开发依赖

    py -3.12 -m venv backend/.venv312
    .\backend\.venv312\Scripts\python.exe -m pip install -r backend/requirements.txt
    .\backend\.venv312\Scripts\python.exe -m pip install PyInstaller==6.22.3
    npm.cmd ci --prefix frontend
    npm.cmd install --prefix "$env:LOCALAPPDATA\TkCRM-Dev\ui-qa" playwright
    & "$env:LOCALAPPDATA\TkCRM-Dev\ui-qa\node_modules\.bin\playwright.cmd" install chromium

PyInstaller 不在 backend/requirements.txt 中，必须额外安装。UI 审计默认从 %LOCALAPPDATA%/TkCRM-Dev/ui-qa/node_modules/playwright 加载依赖；其他位置需设置 PLAYWRIGHT_MODULE 为模块绝对路径。开发工具只用于制包，最终用户不需要 Python、Node、Docker 或 .NET SDK。本机还需要 WebView2 Runtime 才能执行桌面冒烟。

## 3. 打包前检查

版本唯一来源是 backend/app/version.py 的 APP_VERSION。版本变更后，同时更新前端更新日志和 docs/WINDOWS-PACKAGING.md。不要只改版本号而不写变更说明。

先停止当前 TkCRM 窗口，再检查：

    Get-Process TkCrm.Desktop,TkCrm.Server,TkCrm.Updater -ErrorAction SilentlyContinue

保存用户工作后正常关闭，不要按进程名批量强杀。publish.ps1 会删除并重建工作区内的运行包；构建失败时该目录可能只有部分文件，不能启动或交付它。

发布目录不得含真实数据：

    Get-ChildItem .\desktop\runtime\windows-x64 -Recurse -Force -File | Where-Object { $_.Name -eq ".env" -or $_.Extension -in ".db", ".sqlite", ".sqlite3" }

结果必须为空。不要复制真实 .env、monitor.db、邮箱密码、备份或团队数据进入发布目录。

## 4. 构建运行包

从根目录执行：

    powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\desktop\publish.ps1

脚本会构建前端、使用 backend/.venv312 的 PyInstaller 冻结服务器、嵌入 frontend/dist，并发布自包含桌面程序和更新器。主要输出：

- desktop/runtime/windows-x64/TkCrm.Desktop.exe
- desktop/runtime/windows-x64/TkCrm.Updater.exe
- desktop/runtime/windows-x64/server/TkCrm.Server.exe
- desktop/runtime/windows-x64/server/_internal/frontend/dist/

常用日志在 desktop/build/。

## 5. 构建安装器

执行：

    powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\desktop\build-installer.ps1

脚本会验证 Microsoft WebView2 Bootstrapper 签名、读取 APP_VERSION、编译 desktop/installer.iss，生成同版本 Windows 候选清单并自动调用发布审计。输出文件：

    desktop/build/installer/TkCRM-<版本>-win-x64-setup.exe

运行包能启动不等于安装器载荷已更新；准备交付时必须重新执行这一步。

## 6. 发布审计

只审计当前运行包时执行：

    powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\desktop\tests\release-audit.ps1

审计覆盖：运行时数据隔离、前端逐文件哈希一致、更新安全检查、更新进程树清理、窗口几何、高 DPI、失败安装恢复、旧数据库迁移、无 Python/Node/Docker 启动、更新器自动初始化，以及登录/卡密/邮箱页面的多尺寸布局。

必须看到：

    PASS release audit: environment and package checks passed

任何一项失败都不能交付安装器；查看对应 desktop/build 日志，修复后从 publish.ps1 重新开始。

## 7. 人工可见验收

使用 PowerShell 创建隔离配置再打开 EXE；不要直接双击开发运行包访问默认用户数据目录：

    $data = Join-Path $env:TEMP ("TkCRM-visible-" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $data | Out-Null
    $configuration = "JWT_SECRET=isolated-visible-review`nFIELD_ENCRYPTION_KEY=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa`nSUPER_ADMIN_PASSWORD=ReviewOnly123!`n"
    [IO.File]::WriteAllText((Join-Path $data ".env"), $configuration, [Text.UTF8Encoding]::new($false))
    $savedData = $env:TKCRM_DATA_DIR
    try {
      $env:TKCRM_DATA_DIR = $data
      Start-Process .\desktop\runtime\windows-x64\TkCrm.Desktop.exe
    } finally {
      if ($null -eq $savedData) { Remove-Item Env:TKCRM_DATA_DIR -ErrorAction SilentlyContinue }
      else { $env:TKCRM_DATA_DIR = $savedData }
    }

这是合成空库；账号 admin，测试密码 ReviewOnly123!。该密码仅用于隔离夹具，不得用于生产。打开更新日志，确认没有未初始化提示；关闭时确认退出服务。

自动化通过不代表视觉验收完成。阶段性打包后必须打开新运行包，检查：

- 标题栏、任务栏和 EXE 图标是否为当前资源。
- 登录背景、屏幕文字、输入框和按钮是否贴合。
- 侧栏、顶部栏和内容区是否遮挡或变形。
- 卡密页邮箱条、长卡密、按钮和分页是否可见。
- 邮箱页长邮箱、平台标签、展开详情和弹窗是否越界。
- 将窗口缩到约 1180x720，并在不同 DPI 显示器上检查。
- 关闭窗口后，桌面端和它启动的 TkCrm.Server.exe 都退出。

视觉验收应使用临时数据目录，不要打开真实业务数据。自动化截图要展示给产品负责人确认，不能只报告“测试通过”。

## 8. 安装器冒烟

执行：

    powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\desktop\tests\installer-smoke.ps1

它使用临时安装目录和临时数据，验证安装、启动、WebView2 导航、正常退出、卸载和数据保留。

该脚本发现已存在的 TkCRM 安装注册项时会拒绝执行，避免改动用户安装；不要为了跑测试卸载用户实例，改用隔离 Windows 测试环境。此步骤不包含在 release-audit.ps1 内，需独立执行。

## 9. 记录指纹和交接

建议每次构建先创建带时间戳的日志目录，并显式检查两个子进程的退出码：

    $logs = Join-Path $PWD ("desktop/build/stages/" + (Get-Date -Format "yyyyMMdd-HHmmss"))
    New-Item -ItemType Directory -Path $logs -Force | Out-Null
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\desktop\publish.ps1 *> (Join-Path $logs "publish.log")
    if ($LASTEXITCODE -ne 0) { throw "运行包构建失败，查看 $logs/publish.log" }
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\desktop\build-installer.ps1 *> (Join-Path $logs "installer-audit.log")
    if ($LASTEXITCODE -ne 0) { throw "安装器或发布审计失败，查看 $logs/installer-audit.log" }

以上命令实际执行完整构建，不是额外的第二套流程。只有文档或测试夹具变化且载荷不变时，可只执行相关验收并记录未重建；凡是前端、后端、桌面壳、更新器、图标或迁移载荷变化，都要重建交付包。

执行：

    $installer = Get-ChildItem .\desktop\build\installer\TkCRM-*-win-x64-setup.exe | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    Get-FileHash $installer.FullName -Algorithm SHA256
    Get-FileHash .\desktop\runtime\windows-x64\TkCrm.Updater.exe -Algorithm SHA256

把版本、安装器路径、SHA-256、日志、人工验收结果和已知警告追加到 docs/WINDOWS-PACKAGING.md。

同版本重建会覆盖同名安装器。内部阶段包可保留相同版本，但要用时间戳目录归档安装器、日志和哈希；对外更新必须提升版本，不能让不同载荷复用同一发布版本。

记录模板：

    日期 / 版本 / Git 提交与未提交改动：
    本次变更及更新日志：
    安装器路径 / 大小 / SHA-256：
    更新器 SHA-256：
    构建日志 / 发布审计日志 / 退出码：
    隔离安装、卸载、启动、关闭结果：
    可见 UI 验收 / 截图 / 窗口尺寸 / DPI：
    未验证项和已知警告：
    是否提交、推送、上传或部署：

仅生成安装包不会上传 GitHub Release，也不会更新服务器。要让用户通过更新入口下载它，还需单独授权发布 Windows 资产、生成并核对 windows_package_url/windows_sha256 清单。真实下载、安装、重启和失败恢复全链路必须独立验收，代理 idle 不等于升级成功。

每次阶段性打包清单：

- [ ] APP_VERSION、更新日志和打包记录同步。
- [ ] publish.ps1 成功。
- [ ] build-installer.ps1 成功。
- [ ] release-audit.ps1 成功。
- [ ] 隔离安装/卸载通过。
- [ ] 真实可见窗口检查通过。
- [ ] 安装器和更新器 SHA-256 已记录。
- [ ] 没有提交 .env、数据库、备份或临时数据。
- [ ] 未经明确授权，不 commit、push 或部署。

## 10. 常见故障

### 发布时文件被占用

关闭 TkCRM，确认 TkCrm.Desktop.exe、TkCrm.Server.exe 和 TkCrm.Updater.exe 都已退出。不要直接删除整个运行目录。

### 找不到虚拟环境或 apscheduler

确认使用 backend/.venv312/Scripts/python.exe，并重新安装 backend/requirements.txt；不要用系统 Python 直接替代 publish.ps1。

### 更新日志显示尚未初始化更新器

确认启动的是新运行包，并且发布目录包含 TkCrm.Updater.exe。当前桌面端启动会自动初始化本地更新代理；旧安装目录的 EXE 不会自动获得修复。

### 自动化通过但界面看起来变形

记录页面、窗口尺寸、DPI 和截图，修复后重新执行 publish.ps1、build-installer.ps1、release-audit.ps1 和人工验收。

### 安装器已生成但发布审计报错

build-installer.ps1 会先产生 EXE 再执行审计；文件存在不表示可交付。以命令退出码及 PASS release audit 为准，失败包标为不可交付。当前已知 MSB3277 WindowsBase 警告需记录，不要描述为无警告构建。
