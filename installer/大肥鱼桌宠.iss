#define AppName "大肥鱼桌宠"
#define AppVersion "1.0.0"
#define BuildDir GetEnv("FISH_INSTALL_SOURCE")
#define OutputDir GetEnv("FISH_INSTALL_OUTPUT")
#define HdUrl GetEnv("FISH_HD_URL")
#if HdUrl == ""
  #define HdUrl "https://github.com/916099/the-plump-fish-table-pet/releases/download/v1.0.0/Dafeiyu-Pet-HD-Animations-v1.0.0.zip"
#endif
#if BuildDir == ""
  #error 环境变量 FISH_INSTALL_SOURCE 必须指向准备好的发行文件目录
#endif
#if OutputDir == ""
  #error 环境变量 FISH_INSTALL_OUTPUT 必须指向安装器输出目录
#endif
[Setup]
AppId={{7E752AC5-37EC-439C-BED5-012FC2B51968}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=大肥鱼桌宠二创项目
AppPublisherURL=https://github.com/916099/the-plump-fish-table-pet
DefaultDirName={localappdata}\Programs\大肥鱼桌宠
DefaultGroupName=大肥鱼桌宠
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#OutputDir}
OutputBaseFilename=Dafeiyu-Pet-Setup-Windows-x64-v1.0.0
SetupIconFile=..\icon.ico
UninstallDisplayIcon={app}\大肥鱼桌宠.exe
WizardStyle=modern
WizardImageFile=wizard.bmp
WizardSmallImageFile=wizard-small.bmp
WizardImageStretch=yes
Compression=lzma2/fast
SolidCompression=no
CloseApplications=yes
ChangesAssociations=no
[Languages]
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"
[Types]
Name: "standard"; Description: "标准安装（包含标准动画）"
Name: "custom"; Description: "自定义安装（可选高清动画）"; Flags: iscustom
[Components]
Name: "core"; Description: "大肥鱼桌宠与标准动画"; Types: standard custom; Flags: fixed
Name: "hd"; Description: "高清动画（联网下载约 679 MiB）"; Types: custom; ExtraDiskSpaceRequired: 711516278
[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "快捷方式"; Flags: unchecked
[Files]
Source: "{#BuildDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#HdUrl}"; DestName: "Dafeiyu-Pet-HD-Animations-v1.0.0.zip"; DestDir: "{app}"; Hash: "f4b7b16b4644d64e26bac022d525d7acbfa57c43bb3e104b8d37bf070a668912"; ExternalSize: 711516278; Components: hd; Flags: external download extractarchive ignoreversion
[Icons]
Name: "{autoprograms}\大肥鱼桌宠"; Filename: "{app}\大肥鱼桌宠.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\大肥鱼桌宠"; Filename: "{app}\大肥鱼桌宠.exe"; WorkingDir: "{app}"; Tasks: desktopicon
[Run]
Filename: "{app}\大肥鱼桌宠.exe"; Description: "启动大肥鱼桌宠"; Flags: nowait postinstall skipifsilent unchecked
