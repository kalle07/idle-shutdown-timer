
# idle-shutdown-timer

=> download exe and start(need admin righs), GUi open , chose a time and "Start"<br>
shows icon in taskbar<br><br>

multiple check idle shut down timer<br>

  Idle Check Logic (3 × 5s polls = 15s window):<br>
  When will idle timer Reset:<br>
  ⌨/🖱	Mouse/keyboard/touch activity.<br>
  🖥	CPU: Active if ANY poll has ≥1 core >50% OR total usage >12.5% × cores.<br>
  🌐	Network: Active if ALL polls show ≥1 MB/s on at least one NIC.<br>
  ⚠️  Discrete GPU workloads mostly uses one core >50%.<br>
  ⚠️  Virus-scan or Backups mostly uses one core >50%<br>
  🛑  What is not included: some streaming videos or watching local videos!<br>
 
<br>
Useful for anyone who, for example, starts a long download, a simulation, or a training session, so that the computer shuts down, say, 5 minutes after the task is completed. Or perhaps you’re not sure whether you’ll be back in an hour, so you set the timer<br><br>
<img width="690" height="477" alt="grafik" src="https://github.com/user-attachments/assets/6b5ec30b-dfb2-4123-b493-d2529e127539" />

