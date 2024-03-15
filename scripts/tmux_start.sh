
# startup tmux
tmux start-server

# create a new session
tmux new-session -d -s "donbot"

tmux new-window -t donbot:1 -n main
tmux new-window -t donbot:2 -n bot "bash ~/donationbot/scripts/bot.sh"
tmux new-window -t donbot:3 -n syncer "bash ~/donationbot/scripts/syncer.sh"
tmux new-window -t donbot:4 -n boards "bash ~/donationbot/scripts/boards.sh"
#tmux send-keys "htop" C-m


## make 3 vertically even panes
#tmux splitw -h -p 75
#tmux splitw -h -p 50
#
## split left most into 2 on top of each other
#tmux selectp -t 0
#tmux splitw -v -p 50
#
## split next left most into 2 on top of each other
#tmux selectp -t 2
#tmux splitw -v -p 50

# select left top and run htop
#tmux selectp -t 0
#tmux send-keys "htop" C-m
#
## select bottom left and run bot
#tmux selectp -t 1
#tmux send-keys "bash bot.sh" C-m
#
## select middle top and run syncer
#tmux selectp -t 2
#tmux send-keys "bash syncer.sh" C-m
#
## select middle bottom and run boards
#tmux selectp -t 3
#tmux send-keys "bash boards.sh" C-m
#
## select far right and get zsh terminal
#tmux selectp -t 4
#tmux send-keys "zsh" C-m


