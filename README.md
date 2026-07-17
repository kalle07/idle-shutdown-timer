
# idle-shutdown-timer


multiple check idle shut down timer<br>

  "Idle Check Logic (3 × 5s polls = 15s window):\n\n"
  "When will idle timer Reset:\n"
  "⌨/🖱	Mouse/keyboard/touch activity.\n"
  "🖥	CPU: Active if ANY poll has ≥1 core >50% OR total usage >12.5% × cores.\n"
  "🌐	Network: Active if ALL polls show ≥1 MB/s on at least one NIC.\n"
  "⚠️	Note: Discrete GPU workloads mostly uses one core >50%."

