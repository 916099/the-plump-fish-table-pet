#define AppName "大肥鱼桌宠"
#define AppVersion "1.0.0"
#define BuildDir GetEnv("FISH_INSTALL_SOURCE")
#define OutputDir GetEnv("FISH_INSTALL_OUTPUT")
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
Name: "hd"; Description: "高清动画（联网下载约 679 MiB，临时需要约 1.4 GiB 空间）"; Types: custom; ExtraDiskSpaceRequired: 1423032556
[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "快捷方式"; Flags: unchecked
[Files]
Source: "{#BuildDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{autoprograms}\大肥鱼桌宠"; Filename: "{app}\大肥鱼桌宠.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\大肥鱼桌宠"; Filename: "{app}\大肥鱼桌宠.exe"; WorkingDir: "{app}"; Tasks: desktopicon
[Run]
Filename: "{app}\大肥鱼桌宠.exe"; Description: "启动大肥鱼桌宠"; Flags: nowait postinstall skipifsilent unchecked
[Code]
var
  HDDownloadPage: TDownloadWizardPage;

procedure InitializeWizard;
begin
  HDDownloadPage := CreateDownloadPage('下载高清动画', '正在从 GitHub 获取高清动画素材，请保持网络连接。', nil);
  HDDownloadPage.ShowBaseNameInsteadOfUrl := True;
end;

procedure DeinitializeSetup;
begin
  if HDDownloadPage <> nil then
    HDDownloadPage.Free;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  Files: array[0..3] of String;
  Hashes: array[0..3] of String;
  I: Integer;
  PartPath, JoinedPath: String;
  PartStream, JoinedStream: TFileStream;
  ErrorText: String;
begin
  Result := True;
  if (CurPageID = wpReady) and WizardIsComponentSelected('hd') then begin
    Files[0] := 'Dafeiyu-Pet-HD-Animations-v1.0.0.part01';
    Files[1] := 'Dafeiyu-Pet-HD-Animations-v1.0.0.part02';
    Files[2] := 'Dafeiyu-Pet-HD-Animations-v1.0.0.part03';
    Files[3] := 'Dafeiyu-Pet-HD-Animations-v1.0.0.part04';
    Hashes[0] := 'a8dee5d9c74d15b165c9936beec3304551cdc625d85575aebb97c71d208e8387';
    Hashes[1] := '14cc8c4138e002c803c4844ab9f7ffaecd7d2b7e1e52fa0eb366e7f7696b0ecc';
    Hashes[2] := 'f0c1d4b0badf18ab4cc8483b61685e323301c564fb72c312ca1f10f68245f31f';
    Hashes[3] := 'b1f947f4af90188f8567e8277d9773bbf43f1a9d99e06ca7abced7feed2b4e7e';
    HDDownloadPage.Clear;
    for I := 0 to 3 do
      HDDownloadPage.Add('https://github.com/916099/the-plump-fish-table-pet/releases/download/v1.0.0/' + Files[I], Files[I], Hashes[I]);
    HDDownloadPage.Show;
    try
      try
        HDDownloadPage.Download;
        JoinedPath := ExpandConstant('{tmp}\Dafeiyu-Pet-HD-Animations-v1.0.0.zip');
        JoinedStream := TFileStream.Create(JoinedPath, fmCreate);
        try
          for I := 0 to 3 do begin
            PartPath := ExpandConstant('{tmp}\' + Files[I]);
            PartStream := TFileStream.Create(PartPath, fmOpenRead);
            try
              JoinedStream.CopyFrom(PartStream, 0, 1048576);
            finally
              PartStream.Free;
            end;
          end;
        finally
          JoinedStream.Free;
        end;
        ExtractArchive(JoinedPath, ExpandConstant('{app}'), '', True, nil);
      except
        if HDDownloadPage.AbortedByUser then
          ErrorText := '高清动画下载已取消。可以重新运行安装程序并选择标准安装。'
        else
          ErrorText := '高清动画下载或校验失败：' + GetExceptionMessage;
        SuppressibleMsgBox(ErrorText, mbCriticalError, MB_OK, IDOK);
        Result := False;
      end;
    finally
      HDDownloadPage.Hide;
    end;
  end;
end;
