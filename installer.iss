; ═══════════════════════════════════════════════
; BunLauncher — Inno Setup Installer Script
; Создаёт полноценный Windows-установщик
; ═══════════════════════════════════════════════

#define MyAppName "BunLauncher"
#define MyAppVersion "1.0"
#define MyAppPublisher "BunLauncher Team"
#define MyAppURL "https://bunlauncher.com"
#define MyAppExeName "BunLauncher.exe"

[Setup]
AppId={{B8E2F1A0-3C4D-5E6F-7A8B-9C0D1E2F3A4B}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
; Лицензия GPL-3.0
LicenseFile=LICENSE
OutputDir=installer_output
OutputBaseFilename=BunLauncher_Setup
SetupIconFile=assets\bun.ico
; Иконка программы
UninstallDisplayIcon={app}\{#MyAppExeName}
; Сжатие — максимальное LZMA2
Compression=lzma2/ultra64
SolidCompression=yes
LZMAUseSeparateProcess=yes
LZMANumBlockThreads=4
; Внешний вид
WizardStyle=modern
; WizardImageFile=assets\installer_banner.bmp
; WizardSmallImageFile=assets\installer_icon.bmp
; Минимальная версия Windows
MinVersion=10.0
; Размер диска
DiskSpanning=no
; Привилегии — не требуем админа
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
russian.WelcomeLabel=Добро пожаловать в установщик BunLauncher!
russian.FinishLabel=BunLauncher успешно установлен.
english.WelcomeLabel=Welcome to BunLauncher Setup!
english.FinishLabel=BunLauncher has been installed successfully.

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checked
Name: "quicklaunchicon"; Description: "Закрепить на панели задач"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Главный .exe (из PyInstaller)
Source: "dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

; Ассеты (иконки, фон)
Source: "assets\*"; DestDir: "{app}\assets"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; Пуск → Все программы
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Удалить {#MyAppName}"; Filename: "{uninstallexe}"
; Рабочий стол
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
; Запустить после установки
Filename: "{app}\{#MyAppExeName}"; Description: "Запустить {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
// Показать размер установки
function InitializeSetup(): Boolean;
begin
  Result := True;
end;
