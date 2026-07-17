
# idle-shutdown-timer


multiple check idle shut down timer<br>

  Idle Check Logic (3 × 5s polls = 15s window):<br>
  When will idle timer Reset:<br>
  ⌨/🖱	Mouse/keyboard/touch activity.<br>
  🖥	CPU: Active if ANY poll has ≥1 core >50% OR total usage >12.5% × cores.<br>
  🌐	Network: Active if ALL polls show ≥1 MB/s on at least one NIC.<br>
  ⚠️	Note: Discrete GPU workloads mostly uses one core >50%.<br>

