# crewforge ask --verify demo. Regenerate: `vhs docs/demo/ask.tape` from the repo root with crewforge installed, a
# provider configured in the environment (CREWFORGE_PROVIDER/CREWFORGE_MODEL/... — see README) and DEMO_DIR pointing
# at a folder holding the (invented) document shown below (docs/demo/ask/). Output is real; the wait for the model is shown in full.
Output docs/demo/ask.gif

Set Shell "bash"
Set FontSize 16
Set Width 1280
Set Height 760
Set Padding 26
Set Theme { "name": "sasateguh", "black": "#0a0c11", "red": "#ff6a5c", "green": "#7ee0a1", "yellow": "#ffc35a", "blue": "#7aa7ff", "magenta": "#d2a8ff", "cyan": "#4fd1e8", "white": "#c9d1dc", "brightBlack": "#6f7a8e", "brightRed": "#ff8a7a", "brightGreen": "#a6f0c0", "brightYellow": "#ffd68a", "brightBlue": "#a3c2ff", "brightMagenta": "#e2c6ff", "brightCyan": "#8fe6f4", "brightWhite": "#f4f6fa", "background": "#0a0c11", "foreground": "#e6e9ef", "selection": "#232a38", "cursor": "#ff6a2e" }
Set TypingSpeed 35ms

Hide
Type `export PS1='\[\e[38;5;209m\]❯\[\e[0m\] ' COLUMNS=118 && cd "$DEMO_DIR" && clear`
Enter
Sleep 500ms
Show

Type "# A short project brief; one question it answers, one it does not"
Enter
Sleep 400ms
Type "cat kestrel.md"
Enter
Sleep 5s
Type "clear"
Enter
Type `crewforge ask kestrel.md -q "Who must approve a RM 50,000 budget change, and what happens above 4.5 metres?" -q "What will the second phase cost?" --verify`
Enter
Wait+Screen@180s /┘|error/
Sleep 9s
