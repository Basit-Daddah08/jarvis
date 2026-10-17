' ELION (JARVIS) - Reliable Windows Background Launcher
' Runs completely windowless with zero console window.
' Strictly uses the project's own virtual environment pythonw.exe, never global PATH.

Set WshShell = CreateObject("WScript.Shell")
Set FSO = CreateObject("Scripting.FileSystemObject")

AppDir = FSO.GetParentFolderName(WScript.ScriptFullName)
VenvPythonW = AppDir & "\.venv\Scripts\pythonw.exe"
VenvPython = AppDir & "\.venv\Scripts\python.exe"
LauncherScript = AppDir & "\src\launcher.py"

' 1. Check for Virtual Environment Python
TargetPython = ""
If FSO.FileExists(VenvPythonW) Then
    TargetPython = VenvPythonW
ElseIf FSO.FileExists(VenvPython) Then
    TargetPython = VenvPython
Else
    MsgBox "ELION Background Software cannot start:" & vbCrLf & vbCrLf & _
           "The project virtual environment (.venv) was not found at:" & vbCrLf & _
           VenvPythonW & vbCrLf & vbCrLf & _
           "Please run setup.bat in the project directory first to create the environment.", _
           16, "ELION Startup Error"
    WScript.Quit 1
End If

' 2. Check for Launcher Script
If Not FSO.FileExists(LauncherScript) Then
    MsgBox "ELION Startup Error: Cannot find launcher script at:" & vbCrLf & LauncherScript, 16, "ELION Startup Error"
    WScript.Quit 1
End If

' 3. Set Working Directory and Launch Windowless (0 = Hidden, False = Asynchronous Detached)
WshShell.CurrentDirectory = AppDir
LaunchCmd = """" & TargetPython & """ -u """ & LauncherScript & """ start"
WshShell.Run LaunchCmd, 0, False

WScript.Quit 0
