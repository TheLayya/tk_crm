[Setup]
AppId=TkCRM-Isolated-Rollback-Fixture
AppName=TkCRM rollback fixture
AppVersion=0.0.1
DefaultDirName={tmp}\TkCRM-rollback-fixture
PrivilegesRequired=lowest
Uninstallable=no
CreateAppDir=no
CreateUninstallRegKey=no
DisableProgramGroupPage=yes
OutputDir=..\..\build\rollback-fixture
OutputBaseFilename=failure-setup

[Code]
procedure CurStepChanged(CurStep: TSetupStep);
var
  DataDir: String;
  InstallDir: String;
begin
  if CurStep = ssInstall then
  begin
    DataDir := GetEnv('TKCRM_ROLLBACK_FIXTURE_DATA');
    InstallDir := GetEnv('TKCRM_ROLLBACK_FIXTURE_INSTALL');
    if not FileExists(DataDir + '\fixture-only.txt') or not FileExists(InstallDir + '\fixture-only.txt') then
      RaiseException('Missing isolated fixture guard');
    if not SaveStringToFile(InstallDir + '\TkCrm.Desktop.exe', 'failed installer desktop', False) or
       not SaveStringToFile(InstallDir + '\new-only.txt', 'failed installer file', False) or
       not SaveStringToFile(DataDir + '\monitor.db', 'failed installer database', False) or
       not SaveStringToFile(DataDir + '\monitor.db-wal', 'failed installer wal', False) or
       not SaveStringToFile(DataDir + '\.env', 'failed installer configuration', False) or
       not SaveStringToFile(DataDir + '\new-only.txt', 'failed installer data', False) then
      RaiseException('Fixture write failed');
    Abort;
  end;
end;
