while true
do
  export GOOGLE_APPLICATION_CREDENTIALS=~/donationbot/donationbot-edea027e4e1c.json
  source ~/venv/bin/activate
  cd ~/donationbot
  python3 syncer.py
  echo `date`" Syncer Stopped"
  read -p "Press any button or wait 10 seconds to continue.
  " -r -s -n1 -t 2
done
exit
