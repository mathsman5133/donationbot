# break the panes into 5 different windows.
break-pane -s 1.0 -t 2
break-pane -s 1.0 -t 3
break-pane -s 1.0 -t 4
break-pane -s 1.0 -t 5

rename-window -t 2 htop
rename-window -t 3 bot
rename-window -t 4 syncer
rename-window -t 5 boards
