' Lanza el asistente oculto. Ruta relativa a este .vbs (funciona en cualquier carpeta).
Dim fso, dirBase
Set fso = CreateObject("Scripting.FileSystemObject")
dirBase = fso.GetParentFolderName(WScript.ScriptFullName)
Set WshShell = CreateObject("WScript.Shell")
WshShell.Run """" & dirBase & "\venv\Scripts\pythonw.exe"" """ & dirBase & "\voice_assistant.py""", 0, False