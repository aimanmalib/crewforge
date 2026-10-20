# crewforge review demo. Regenerate: `vhs docs/demo/review.tape` with crewforge installed and a provider configured
# (env: CREWFORGE_PROVIDER/CREWFORGE_MODEL/... — see README). Output is real; the wait for the model is shown in full.
Output docs/demo/review.gif

Set Shell "bash"
Set FontSize 16
Set Width 1280
Set Height 760
Set Padding 26
Set Theme { "name": "sasateguh", "black": "#0a0c11", "red": "#ff6a5c", "green": "#7ee0a1", "yellow": "#ffc35a", "blue": "#7aa7ff", "magenta": "#d2a8ff", "cyan": "#4fd1e8", "white": "#c9d1dc", "brightBlack": "#6f7a8e", "brightRed": "#ff8a7a", "brightGreen": "#a6f0c0", "brightYellow": "#ffd68a", "brightBlue": "#a3c2ff", "brightMagenta": "#e2c6ff", "brightCyan": "#8fe6f4", "brightWhite": "#f4f6fa", "background": "#0a0c11", "foreground": "#e6e9ef", "selection": "#232a38", "cursor": "#ff6a2e" }
Set TypingSpeed 35ms

Hide
Type `export PS1='\[\e[38;5;209m\]❯\[\e[0m\] ' && cd "$DEMO_DIR" && clear`
Enter
Sleep 500ms
Show

Type "# A login function with a bug a code reviewer must catch"
Enter
Sleep 400ms
Type "cat login.py"
Enter
Sleep 3s
Type "clear"
Enter
Type "crewforge review login.py 2> usage.log | head -n 32"
Enter
Wait+Screen@180s /Critical|failed/
Sleep 7s
