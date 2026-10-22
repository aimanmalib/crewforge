# crewforge academic feedback demo, in Bahasa Melayu. Regenerate: `vhs docs/demo/academic.tape` from the repo root with
# crewforge installed, a provider configured in the environment (CREWFORGE_PROVIDER/CREWFORGE_MODEL/... — see README)
# and DEMO_DIR pointing at a folder holding the draft and brief shown below (docs/demo/academic/).
# The draft, brief, names and reference are invented for the demo. Output is real; the wait for the model is shown in full.
Output docs/demo/academic.gif

Set Shell "bash"
Set FontSize 15
Set Width 1280
Set Height 1040
Set Padding 26
Set Theme { "name": "sasateguh", "black": "#0a0c11", "red": "#ff6a5c", "green": "#7ee0a1", "yellow": "#ffc35a", "blue": "#7aa7ff", "magenta": "#d2a8ff", "cyan": "#4fd1e8", "white": "#c9d1dc", "brightBlack": "#6f7a8e", "brightRed": "#ff8a7a", "brightGreen": "#a6f0c0", "brightYellow": "#ffd68a", "brightBlue": "#a3c2ff", "brightMagenta": "#e2c6ff", "brightCyan": "#8fe6f4", "brightWhite": "#f4f6fa", "background": "#0a0c11", "foreground": "#e6e9ef", "selection": "#232a38", "cursor": "#ff6a2e" }
Set TypingSpeed 35ms

Hide
Type `export PS1='\[\e[38;5;209m\]❯\[\e[0m\] ' COLUMNS=112 && cd "$DEMO_DIR" && clear`
Enter
Sleep 500ms
Show

Type "# A student's essay draft in Malay: one overclaim, one citation missing from the reference list"
Enter
Sleep 400ms
Type "cat draf.md"
Enter
Sleep 5s
Type "clear"
Enter
Type "crewforge academic feedback draf.md --brief taklimat.md --language ms --reviewer argument 2> guna.log"
Enter
Wait+Screen@180s /Semakan sitasi|error/
Sleep 9s
