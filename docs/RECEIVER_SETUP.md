# Receiver (Onkyo TX-RZ50) setup

htTamer controls the receiver over your network at its IP address (for example **192.168.1.50**; set it in Setup → Receiver).
Control already works: power, input, listening mode, volume down, mute and subwoofer level.

## One step needed for the automatic blend test

> **Status (Nov 12, 2026): working.** The Python firewall rules were switched to Allow, and the
> receiver fetched and played a test file. The narrower rule below is optional, if you want
> to tighten things up again.

The **Blend the subs with your speakers** test plays a test file through the receiver.
In *Automatic (network)* mode the receiver fetches that file from this PC, which Windows Firewall
blocked at first (Python had "Block" rules, and the Wi-Fi network "CDC - IoT" is set to Public).

htTamer doesn't change firewall settings itself. To allow **only the receiver**, and only on
htTamer's media port (8790), run these two lines in **PowerShell as Administrator**:

```powershell
Get-NetFirewallApplicationFilter | Where-Object Program -eq 'C:\Users\<you>\AppData\Local\Programs\Python\Python312\python.exe' | Get-NetFirewallRule | Where-Object Action -eq 'Block' | Disable-NetFirewallRule
New-NetFirewallRule -DisplayName 'htTamer: receiver fetches test file' -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8790 -RemoteAddress 192.168.1.50 -Program 'C:\Users\<you>\AppData\Local\Programs\Python\Python312\python.exe'
```

* Line 1 disables the two "block Python" rules. Windows still blocks anything not explicitly
  allowed, so this doesn't open Python up to the network.
* Line 2 allows exactly one thing: the receiver (192.168.1.50) fetching from port 8790.
* To undo: `Remove-NetFirewallRule -DisplayName 'htTamer: receiver fetches test file'`.

The same commands appear in the Receiver screen if a blend test fails because of the firewall.

## No firewall change? Use a USB stick

Choose **USB stick** in the blend test, download `httamer_blend_test.wav` from the link
shown, copy it to a USB stick, plug it into the receiver, press **Run blend test**, then play
the file from the receiver's USB input when asked. htTamer listens for the sweeps itself.

## What the blend test can change
* **Subs a little early:** htTamer adds delay in the miniDSP (a new saved tune, applied
  to the slot that's playing).
* **Subs late:** a receiver setting. Increase *Subwoofer distance* in the RZ50's speaker
  setup by the amount shown. The miniDSP can only add delay, never remove it.
* **Sub level:** one click sets the receiver's subwoofer level (raising asks first).
* Volume is never raised automatically. Input, listening mode, volume and power are restored
  after every test.
