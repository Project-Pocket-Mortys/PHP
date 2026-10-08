<?php
declare(strict_types=1);
require __DIR__ . "/../auth.php";
$user = require_user($pdo);

/* =========================
   CHECK FOR LINK
   ========================= */
  $email = $_SESSION["user"]["email"] ?? null;
  if (!empty($email)){
  $stmt = $pdo->prepare("SELECT email,recovery_code_hash FROM registered_users WHERE email = ?");
  $stmt->execute([$email]);
  $get_hash = $stmt->fetch();
  $got_hash = $get_hash['recovery_code_hash'];
  
  $stmt = $pdo->prepare("SELECT recovery_code_hash,player_id,username,level,xp,xp_lower,xp_upper,player_avatar_id FROM users WHERE recovery_code_hash = ?");
  $stmt->execute([$got_hash]);
  $get_player = $stmt->fetch();
  
  $username = $get_player["username"] ?? null;
  }
?>
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
  <meta name="color-scheme" content="light dark" />
  <title>Portal Dashboard</title>

  <style>
    :root{
      --bg: #04070d;
      --card: rgba(8, 14, 20, 0.75);
      --card-border: rgba(120, 255, 80, 0.22);
      --text: rgba(235, 255, 245, 0.96);
      --muted: rgba(235, 255, 245, 0.68);
      --shadow: 0 22px 60px rgba(0,0,0,0.55);

      --primary: #38ff6a;
      --primary-2: #2ee8ff;

      --field: rgba(255,255,255,0.06);
      --field-border: rgba(183,255,60,0.22);
      --field-focus: rgba(56,255,106,0.28);

      --radius: 18px;
      --font: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, "Apple Color Emoji","Segoe UI Emoji";
    }

    *{ box-sizing:border-box; }
    html,body{ height:100%; }

    body{
      margin:0;
      font-family: var(--font);
      color: var(--text);
      background:
        radial-gradient(1200px 700px at 20% 20%, rgba(56,255,106,0.22), transparent 55%),
        radial-gradient(900px 600px at 80% 15%, rgba(46,232,255,0.18), transparent 52%),
        radial-gradient(900px 700px at 70% 85%, rgba(183,255,60,0.10), transparent 55%),
        var(--bg);
      -webkit-font-smoothing: antialiased;
      -moz-osx-font-smoothing: grayscale;
      padding: 22px;
    }

    .wrap{
      max-width: 980px;
      margin: 0 auto;
      display:grid;
      gap: 14px;
    }

    .topbar{
      display:flex;
      align-items:center;
      justify-content:space-between;
      gap: 12px;
      padding: 14px 16px;
      border-radius: var(--radius);
      border: 1px solid var(--card-border);
      background: var(--card);
      box-shadow: var(--shadow);
      backdrop-filter: blur(12px);
      -webkit-backdrop-filter: blur(12px);
    }

    .brand{
      display:flex;
      align-items:center;
      gap: 10px;
      min-width: 0;
    }

    .logo{
      width: 42px; height: 42px;
      border-radius: 14px;
      background: linear-gradient(135deg, var(--primary), var(--primary-2));
      box-shadow: 0 14px 35px rgba(56,255,106,0.16);
      display:grid;
      place-items:center;
      flex: 0 0 auto;
    }
    .logo::after{
      content:"";
      width: 16px; height: 16px;
      border-radius: 50%;
      box-shadow: 0 0 0 2px rgba(5,10,8,0.6) inset;
      background: radial-gradient(circle at 35% 35%, rgba(255,255,255,0.9), rgba(255,255,255,0.0) 55%),
                  radial-gradient(circle at 50% 50%, rgba(0,0,0,0.2), rgba(0,0,0,0) 60%);
      opacity: .9;
    }

    .brand h1{
      margin:0;
      font-size: 16px;
      letter-spacing: -0.02em;
      white-space: nowrap;
      overflow:hidden;
      text-overflow: ellipsis;
    }
    .brand p{
      margin:0;
      color: var(--muted);
      font-size: 13px;
      white-space: nowrap;
      overflow:hidden;
      text-overflow: ellipsis;
    }

    .btn{
      border: 0;
      border-radius: 14px;
      padding: 11px 14px;
      cursor:pointer;
      font-weight: 650;
      font-size: 13px;
      display:flex;
      align-items:center;
      justify-content:center;
      gap: 10px;
      transition: transform .06s ease, filter .15s ease, opacity .15s ease;
      user-select:none;
      background: rgba(255,255,255,0.06);
      border: 1px solid var(--card-border);
      color: var(--text);
      text-decoration:none;
    }
    .btn:active{ transform: translateY(1px); }
    .btn:hover{ filter: brightness(1.05); }

    .grid{
      display:grid;
      grid-template-columns: 1.2fr 0.8fr;
      gap: 14px;
    }
    @media (max-width: 860px){
      .grid{ grid-template-columns: 1fr; }
    }

    .card{
      border-radius: var(--radius);
      border: 1px solid var(--card-border);
      background: var(--card);
      box-shadow: var(--shadow);
      backdrop-filter: blur(12px);
      -webkit-backdrop-filter: blur(12px);
      padding: 16px;
    }

    .card h2{
      margin: 0 0 8px;
      font-size: 15px;
      letter-spacing: -0.02em;
    }
    .muted{ color: var(--muted); font-size: 13px; line-height: 1.45; }

    .big{
      font-size: 22px;
      margin: 6px 0 2px;
      letter-spacing: -0.02em;
    }

    .pill{
      display:inline-flex;
      align-items:center;
      gap: 8px;
      padding: 9px 10px;
      border-radius: 14px;
      border: 1px solid rgba(255,255,255,0.10);
      background: rgba(255,255,255,0.04);
      font-size: 13px;
      color: var(--muted);
    }
    .dot{
      width: 10px; height: 10px;
      border-radius: 999px;
      background: linear-gradient(135deg, var(--primary), var(--primary-2));
      box-shadow: 0 0 20px rgba(56,255,106,0.18);
    }

    .primary{
      background: linear-gradient(135deg, var(--primary), var(--primary-2));
      color: #05110a;
      border: 0;
      box-shadow: 0 14px 35px rgba(56,255,106,0.14);
    }

    .codeBox{
      margin-top: 10px;
      padding: 12px;
      border-radius: 14px;
      border: 1px dashed rgba(183,255,60,0.35);
      background: rgba(0,0,0,0.18);
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
      font-size: 16px;
      letter-spacing: 0.08em;
      text-align:center;
      display:none;
    }

    .msg{
      margin-top: 10px;
      padding: 12px;
      border-radius: 14px;
      font-size: 13px;
      border: 1px solid transparent;
      display:none;
    }
    .msg.ok{ background: rgba(43,213,118,0.10); border-color: rgba(43,213,118,0.22); }
    .msg.err{ background: rgba(255,77,109,0.12); border-color: rgba(255,77,109,0.22); }

    .rowBtns{
      display:flex;
      gap: 10px;
      flex-wrap: wrap;
      margin-top: 12px;
    }
	.section-text{
    margin-top: 6px;
    margin-bottom: 16px;
    }

    .section-actions{
    margin-top: 12px;
    margin-bottom: 14px;
    }

    .section-feedback{
    margin-top: 8px;
    }

    .codeBox{
    margin-top: 10px;
    }

    .msg{
    margin-top: 10px;
    }
	.account-info{
	margin-top: 10px;
	font-size: 14.5px; /* slightly bigger than muted */
	color: var(--text);
	}
    /*
   .info-row{
	display: flex;
	justify-content: space-between;
	align-items: center;
	padding: 6px 0;
	border-bottom: 1px solid rgba(255,255,255,0.08);
	}

   .info-row:last-child{
 	border-bottom: none;
	}
	*/
   .info-row{
  	display: flex;
  	justify-content: flex-start; /* align items to the left */
  	align-items: center;
  	gap: 8px; /* optional: space between items */
  	padding: 6px 0;
  	border-bottom: 1px solid rgba(255,255,255,0.08);
	}

   .info-row:last-child{
  	border-bottom: none;
	}


	.label{
	color: var(--muted);
	font-size: 13px;
	}

	.value{
	font-weight: 600;
	font-size: 15px;
	color: var(--text);
	}

	.info-note{
	margin-top: 12px;
	font-size: 13.5px;
	color: var(--muted);
	line-height: 1.5;
	}

	.link-btn{
	margin-top: 12px;
	display: inline-flex;
	text-decoration: none;
	}
	.xpHUD{
	display:flex;
	align-items:center;
	gap:10px;
	width:min(520px, 100%);
	}

	.lvlBadge{
	padding: 6px 10px;
	font-weight: 800;
	font-size: 14px;
	letter-spacing: .02em;
	color: #eaf7ff;
	background: rgba(0,0,0,.65);
	border: 2px solid rgba(255,255,255,.18);
	border-radius: 10px;
	box-shadow: 0 6px 18px rgba(0,0,0,.35);
	white-space: nowrap;
	}

	.xpBar{
	position:relative;
	height: 20px;
	flex:1;
	border-radius: 10px;
	background: rgba(0,0,0,.55);
	border: 2px solid rgba(255,255,255,.14);
	overflow:hidden;
	box-shadow: inset 0 0 0 1px rgba(0,0,0,.35), 0 6px 18px rgba(0,0,0,.25);
	}

	.xpFill{
	height:100%;
	width:0%;
	border-radius: 8px;
	background: linear-gradient(180deg,
  	  rgba(255,198,77,1) 0%,
  	  rgba(255,147,30,1) 55%,
  	  rgba(230,90,0,1) 100%
	  );
 	 box-shadow: inset 0 1px 0 rgba(255,255,255,.35),
 	             0 0 18px rgba(255,140,0,.22);
 	 transition: width .35s ease;
	}

	.xpGloss{
 	 position:absolute;
 	 inset:0;
 	 background: linear-gradient(180deg, rgba(255,255,255,.18), rgba(255,255,255,0) 55%);
	  pointer-events:none;
	}

	.xpText{
	position:absolute;
	inset:0;
	display:flex;
	align-items:center;
	justify-content:center;
	font-size: 12px;
	font-weight: 700;
	color: rgba(255,255,255,.92);
	text-shadow: 0 1px 2px rgba(0,0,0,.65);
	pointer-events:none;
	}

	/* Make the XP row full-width (don't use the label/value split layout) */
	.info-row.xp-row{
  	justify-content: flex-start; /* stops space-between behavior */
 	 align-items: stretch;
	}

	/* Force the inner wrapper to take the full row width */
	.info-row.xp-row > div{
 	 width: 100%;
	}

	/* Let the HUD expand to row width */
	.info-row.xp-row .xpHUD{
 	 width: 100%;
 	 max-width: none; /* overrides the 520px cap if you want full width */
	}
	
	.info-row.center-row{
	justify-content: center;   /* center horizontally */
	}

	.info-row.center-row .value{
	text-align: center;
	}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="topbar">
      <div class="brand">
        <div class="logo" aria-hidden="true"></div>
        <div style="min-width:0">
          <h1>Portal Dashboard</h1>
          <p><?= htmlspecialchars($user["email"]) ?></p>
        </div>
		<?php if (!empty($username)): ?>
      <div class="pill">
		<span class="dot"></span>
		Connected to <?= htmlspecialchars($username) ?>
		</div>
		<?php endif; ?>
      </div>
      <a class="btn" href="/../?logout">Logout</a>
    </div>

    <div class="grid">
      <section class="card">
		<div class="big">Welcome</div>
        <div class="account-info">

        </div>
      </section>
      <aside class="card">
        <h2>Account</h2>
          <div class="info-row">
            <span class="label">Player ID</span>
            <span class="value"><?= htmlspecialchars($get_player['player_id'] ?? "Not linked") ?></span>
          </div>

          <div class="info-row">
            <span class="label">Username</span>
            <span class="value"><?= htmlspecialchars($get_player['username'] ?? "Not linked") ?></span>
          </div>
		  
		  <div class="info-row center-row">
            <span class="value"><?= htmlspecialchars($get_player['player_avatar_id'] ?? "Not linked") ?></span>
          </div>

		  
          <div class="info-row xp-row">
		  <?php if ($get_player) {
		  $level    = (int)($get_player["level"] ?? 1);

  		  // lifetime totals
  		  $xpTotal  = (int)($get_player["xp"] ?? 0);
  		  $xpLower  = (int)($get_player["xp_lower"] ?? 0);
  		  $xpUpper  = (int)($get_player["xp_upper"] ?? 0);

  		  // safety: ensure bounds make sense
  		  if ($xpUpper <= $xpLower) {
    		  // fallback so UI doesn't explode
    		  $xpLower = 0;
    		  $xpUpper = max(1, $xpTotal);
  		  }

  		  // progress into current level
  		  $xpIntoLevel = $xpTotal - $xpLower;
  		  $xpThisLevel = $xpUpper - $xpLower;

  		  // clamp
  		  if ($xpIntoLevel < 0) $xpIntoLevel = 0;
  		  if ($xpIntoLevel > $xpThisLevel) $xpIntoLevel = $xpThisLevel;

  		  $progressPct = ($xpThisLevel > 0) ? (($xpIntoLevel / $xpThisLevel) * 100) : 0;
  		  if ($progressPct < 0) $progressPct = 0;
  		  if ($progressPct > 100) $progressPct = 100;
		  ?>
            <div style="padding-top:10px;">
              <div class="xpHUD" role="group" aria-label="Level and experience">
                <div class="lvlBadge">LVL <?= (int)$level ?></div>

                <div class="xpBar" aria-label="Experience bar">
                  <div class="xpFill" style="width: <?= number_format($progressPct, 2, '.', '') ?>%;"></div>
                  <div class="xpGloss"></div>
                  <div class="xpText">
                    <?= number_format($xpIntoLevel) ?> / <?= number_format($xpThisLevel) ?> XP
                  </div>
                </div>
              </div>
            </div>
          </div>
      </aside>

		<?php } if (empty($get_player) && !empty($got_hash)): ?>
            <div class="info-note">
              This is your dashboard. Account information will become available once you link your account. Go into the game on your phone and go to settings and click Faq then login to your account and the select Link Account.
            </div>
			<?php
            $userAgent = strtolower($_SERVER['HTTP_USER_AGENT']);
            if (stripos($userAgent, 'android') !== false) {
			?>
            <a class="btn primary link-btn"
               href="pocketmortys://Braze?LinkAccount=<?php echo $got_hash; ?>">
              Link Account
            </a>
			<?php } endif; ?>
        </div>

        <?php if (empty($got_hash)): ?>
		<div class="info-note">
              Generate a code so you can link your accounts.
            </div>
        <div class="rowBtns">
          <button class="btn primary" id="btnGen">Generate Recovery Code</button>
          <button class="btn" id="btnCopy" style="display:none;">Copy</button>
        </div>

        <div id="codeBox" class="codeBox"></div>
        <div id="msgOk" class="msg ok"></div>
        <div id="msgErr" class="msg err"></div>
      </section>

      <aside class="card">
        <h2>Security Tips</h2>
        <div class="muted">
          • Save your code in a password manager.<br>
          • Don’t screenshot it on shared devices.<br>
        </div>
      </aside>
	  <?php endif; ?>
    </div>
  </div>
<?php if (empty($got_hash)): ?>
  <script>
    const btnGen = document.getElementById("btnGen");
    const btnCopy = document.getElementById("btnCopy");
    const codeBox = document.getElementById("codeBox");
    const msgOk = document.getElementById("msgOk");
    const msgErr = document.getElementById("msgErr");

    function showOk(t){ msgErr.style.display="none"; msgOk.textContent=t; msgOk.style.display="block"; }
    function showErr(t){ msgOk.style.display="none"; msgErr.textContent=t; msgErr.style.display="block"; }

    btnGen.addEventListener("click", async () => {
      msgOk.style.display = "none";
      msgErr.style.display = "none";
      codeBox.style.display = "none";
      btnCopy.style.display = "none";

      btnGen.disabled = true;

      try{
        const res = await fetch("/../generate.php", {
          method:"POST",
          headers:{ "Content-Type":"application/json" },
          body: JSON.stringify({})
        });

        const text = await res.text();
        let json;
        try { json = JSON.parse(text); } catch { json = null; }

        if (!res.ok || !json || !json.success){
          return showErr((json && (json.message || json.error)) ? (json.message || json.error) : (text || "Failed."));
        }

        const code = json.recovery_code;
		const message = json.message;
        codeBox.textContent = code;
        codeBox.style.display = "block";
        btnCopy.style.display = "inline-flex";
        showOk(message);

      } catch(e){
        showErr("Network error. Try again.");
      } finally {
        btnGen.disabled = false;
      }
    });

    btnCopy.addEventListener("click", async () => {
      try{
        await navigator.clipboard.writeText(codeBox.textContent);
        showOk("Copied to clipboard. Save it somewhere safe. Refresh page once saved.");
      } catch(e){
        showErr("Copy failed. You can manually select and copy the code.");
      }
    });
  </script>
<?php endif; ?>
</body>
</html>
