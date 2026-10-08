<?php
declare(strict_types=1);
if(isset($_GET['logout'])){
require __DIR__ . "/auth.php";

if (session_status() !== PHP_SESSION_ACTIVE) {
  session_start();
}

// If you store token in session or cookie, clean it up
$token = $_SESSION["token"] ?? ($_COOKIE[$COOKIE_NAME] ?? null);

if ($token) {
  $hash = token_hash($token);

  // Remove token from DB (invalidate session)
  $stmt = $pdo->prepare("DELETE FROM user_sessions WHERE token_hash = ?");
  $stmt->execute([$hash]);
}

// Clear remember-me cookie
clear_remember_cookie();

// Destroy PHP session
$_SESSION = [];
if (ini_get("session.use_cookies")) {
  $params = session_get_cookie_params();
  setcookie(
    session_name(),
    "",
    time() - 42000,
    $params["path"],
    $params["domain"],
    $params["secure"],
    $params["httponly"]
  );
}
session_destroy();

// Redirect to login page
header("Location: /");
exit;
}
?>
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
  <meta name="color-scheme" content="light dark" />
  <title>Support</title>

  <style>
    :root{
  /* Keep your original spacing system — only change colors */
  --bg: #04070d;
  --card: rgba(8, 14, 20, 0.75);
  --card-border: rgba(120, 255, 80, 0.22);
  --text: rgba(235, 255, 245, 0.96);
  --muted: rgba(235, 255, 245, 0.68);
  --shadow: 0 22px 60px rgba(0,0,0,0.55);

  /* Map portal colors into the SAME variable names your layout uses */
  --primary: #38ff6a;     /* portal green */
  --primary-2: #2ee8ff;   /* lab cyan */

  --field: rgba(255,255,255,0.06);
  --field-border: rgba(183,255,60,0.22);
  --field-focus: rgba(56,255,106,0.28);

  --radius: 18px;

  --font: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, "Apple Color Emoji","Segoe UI Emoji";
}

/* Optional: light mode portal version (keeps your structure) */
@media (prefers-color-scheme: light) {
  :root{
    --bg: #f4fff8;
    --card: rgba(255,255,255,0.90);
    --card-border: rgba(30,80,45,0.14);
    --text: rgba(10,20,40,0.92);
    --muted: rgba(10,20,40,0.62);
    --shadow: 0 22px 60px rgba(12,18,30,0.12);

    --field: rgba(10,20,40,0.04);
    --field-border: rgba(30,80,45,0.18);
    --field-focus: rgba(56,255,106,0.18);
  }
}

*{ box-sizing:border-box; }
html,body{ height:100%; }

body{
  margin:0;
  font-family: var(--font);
  color: var(--text);

  /* Portal background but with your original “3-radials + base” style */
  background:
    radial-gradient(1200px 700px at 20% 20%, rgba(56,255,106,0.26), transparent 55%),
    radial-gradient(900px 600px at 80% 15%, rgba(46,232,255,0.20), transparent 52%),
    radial-gradient(900px 700px at 70% 85%, rgba(183,255,60,0.12), transparent 55%),
    var(--bg);

  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

/* OPTIONAL: keep your page static (no crazy animation) */
/* If you want a subtle “portal shimmer” add this back later. */

.center-wrap{
  min-height: 100svh;
  display:flex;
  align-items:center;
  justify-content:center;
  padding: 24px;
}

.card{
  width: 100%;
  max-width: 420px;
  border-radius: var(--radius);
  border: 1px solid var(--card-border);
  background: var(--card);
  box-shadow: var(--shadow);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  padding: calc(20px + env(safe-area-inset-top)) 20px calc(20px + env(safe-area-inset-bottom));
}
@media (min-width: 520px){
  .card{ padding: 26px; }
}

.card h2{
  margin: 0 0 6px;
  font-size: 20px;
  letter-spacing: -0.02em;
}

.sub{
  margin: 0 0 18px;
  color: var(--muted);
  font-size: 14px;
  line-height: 1.45;
}

form{ display:grid; gap: 12px; }

label{
  display:block;
  font-size: 13px;
  color: var(--muted);
  margin: 0 0 6px;
}

.field{ position:relative; display:block; }

input{
  width:100%;
  padding: 14px 14px;
  border-radius: 14px;
  border: 1px solid var(--field-border);
  background: var(--field);
  color: var(--text);
  outline:none;
  font-size: 15px;
  transition: box-shadow .15s ease, border-color .15s ease;
}
input:focus{
  border-color: rgba(56,255,106,0.65); /* portal focus */
  box-shadow: 0 0 0 4px var(--field-focus);
}

.toggle{
  position:absolute;
  right: 10px;
  top: 50%;
  transform: translateY(-50%);
  border: 0;
  background: transparent;
  color: var(--muted);
  padding: 8px 10px;
  border-radius: 12px;
  cursor:pointer;
  font-size: 13px;
}
.toggle:hover{ background: rgba(255,255,255,0.06); color: var(--text); }

/* ✅ FIXED remember/forgot row (keeps your spacing) */
.row{
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap: 12px;
  margin-top: 2px;
}

.check{
  display:inline-flex;     /* was flex */
  align-items:center;
  gap: 8px;                /* keep your original gap */
  font-size: 13px;
  color: var(--muted);
  user-select:none;
  white-space: nowrap;     /* prevent wrap */
}

.check input[type="checkbox"]{
  width: 16px;
  height: 16px;
  padding: 0;
  margin: 0;               /* fixes Android spacing */
  flex: 0 0 auto;
  accent-color: var(--primary); /* portal green */
}

.row .link{
  margin-left: auto;       /* forces right alignment */
  white-space: nowrap;
}

/* Keep link styles exactly like your original */
.link{
  color: var(--muted);
  text-decoration:none;
  font-size: 13px;
}
.link:hover{ color: var(--text); text-decoration: underline; }

.btn{
  border: 0;
  border-radius: 14px;
  padding: 13px 14px;
  cursor:pointer;
  font-weight: 650;
  font-size: 14px;
  display:flex;
  align-items:center;
  justify-content:center;
  gap: 10px;
  transition: transform .06s ease, filter .15s ease, opacity .15s ease;
  user-select:none;
}
.btn:active{ transform: translateY(1px); }
.btn[disabled]{ opacity:0.65; cursor:not-allowed; }

.btn-primary{
  background: linear-gradient(135deg, var(--primary), var(--primary-2));
  color: #05110a; /* readable on neon */
  box-shadow: 0 14px 35px rgba(56,255,106,0.18);
}
.btn-primary:hover{ filter: brightness(1.05); }

.btn-ghost{
  background: rgba(255,255,255,0.06);
  border: 1px solid var(--card-border);
  color: var(--text);
}

.divider{
  display:flex;
  align-items:center;
  gap: 12px;
  margin: 6px 0;
  color: var(--muted);
  font-size: 12px;
}
.divider::before, .divider::after{
  content:"";
  height:1px;
  flex:1;
  background: rgba(255,255,255,0.14);
}

.error, .ok{
  display:none;
  padding: 12px 12px;
  border-radius: 14px;
  font-size: 13px;
  line-height: 1.35;
  border: 1px solid transparent;
}
.error{
  background: rgba(255,77,109,0.12);
  border-color: rgba(255,77,109,0.22);
}
.ok{
  background: rgba(43,213,118,0.10);
  border-color: rgba(43,213,118,0.22);
}

.footer{
  margin-top: 14px;
  color: var(--muted);
  font-size: 13px;
  text-align:center;
}

.spinner{
  width: 16px;
  height: 16px;
  border-radius: 50%;
  border: 2px solid rgba(255,255,255,0.55);
  border-top-color: rgba(255,255,255,0.0);
  animation: spin 0.8s linear infinite;
  display:none;
}
.loading .spinner{ display:inline-block; }

@keyframes spin { to { transform: rotate(360deg); } }

  </style>
</head>

<body>
  <main class="center-wrap">
    <section class="card" aria-label="Sign in">
      <h2>Portal Login</h2>
      <p class="sub">Use your email and password, or continue with Google.</p>

      <div id="msgError" class="error" role="alert"></div>
      <div id="msgOk" class="ok" role="status"></div>

      <form id="loginForm" autocomplete="on">
        <div>
          <label for="email">Email</label>
          <div class="field">
            <input id="email" name="email" type="email" inputmode="email" autocomplete="email"
                   placeholder="you@example.com" required />
          </div>
        </div>

        <div>
          <label for="password">Password</label>
          <div class="field">
            <input id="password" name="password" type="password" autocomplete="current-password"
                   placeholder="••••••••" required minlength="6" />
            <button class="toggle" type="button" id="togglePw" aria-label="Show password">Show</button>
          </div>
        </div>

		<div class="row">
          <label class="check">
            <input type="checkbox" id="remember" />
            <span>Remember me</span>
          </label>
          <a class="link" href="#" id="forgotLink">Forgot password?</a>
        </div>


        <button class="btn btn-primary" id="btnLogin" type="submit">
          <span class="spinner" aria-hidden="true"></span>
          <span class="btn-text">Enter Portal</span>
        </button>

        <div class="divider">or</div>

        <button class="btn btn-ghost" type="button" id="btnGoogle">
          <svg width="18" height="18" viewBox="0 0 48 48" aria-hidden="true">
            <path fill="#FFC107" d="M43.6 20.1H42V20H24v8h11.3C33.7 32.7 29.3 36 24 36c-6.6 0-12-5.4-12-12s5.4-12 12-12c3.1 0 5.9 1.2 8 3.1l5.7-5.7C34.2 6.1 29.4 4 24 4 12.9 4 4 12.9 4 24s8.9 20 20 20 20-8.9 20-20c0-1.3-.1-2.6-.4-3.9z"/>
            <path fill="#FF3D00" d="M6.3 14.7l6.6 4.8C14.7 15.1 19 12 24 12c3.1 0 5.9 1.2 8 3.1l5.7-5.7C34.2 6.1 29.4 4 24 4c-7.7 0-14.4 4.3-17.7 10.7z"/>
            <path fill="#4CAF50" d="M24 44c5.2 0 9.9-2 13.4-5.2l-6.2-5.2C29.2 35.3 26.7 36 24 36c-5.3 0-9.8-3.4-11.4-8.1l-6.5 5C9.3 39.5 16.1 44 24 44z"/>
            <path fill="#1976D2" d="M43.6 20.1H42V20H24v8h11.3c-1 2.6-2.9 4.7-5.3 6.2l6.2 5.2C39.7 36.4 44 31 44 24c0-1.3-.1-2.6-.4-3.9z"/>
          </svg>
          Continue with Google
        </button>

        <p class="footer">
          <a class="link" href="#" id="createLink">Don’t have an account? Create one</a>
        </p>
      </form>
    </section>
  </main>

  <script>
    const LOGIN_ENDPOINT = "login.php";
	const REGISTER_ENDPOINT = "register.php";

    const form = document.getElementById("loginForm");
    const btnLogin = document.getElementById("btnLogin");
    const msgError = document.getElementById("msgError");
    const msgOk = document.getElementById("msgOk");

    function showError(text){
      msgOk.style.display = "none";
      msgError.textContent = text;
      msgError.style.display = "block";
    }
    function showOk(text){
      msgError.style.display = "none";
      msgOk.textContent = text;
      msgOk.style.display = "block";
    }

    const pw = document.getElementById("password");
    const togglePw = document.getElementById("togglePw");
    togglePw.addEventListener("click", () => {
      const isHidden = pw.type === "password";
      pw.type = isHidden ? "text" : "password";
      togglePw.textContent = isHidden ? "Hide" : "Show";
      pw.focus();
    });

    document.getElementById("forgotLink").addEventListener("click", (e) => {
      e.preventDefault();
      showError("Forgot password flow not wired yet.");
    });
    document.getElementById("createLink").addEventListener("click", (e) => {
      e.preventDefault();
      showOk("Create account flow not wired yet.");
    });

    document.getElementById("btnGoogle").addEventListener("click", () => {
      showOk("Google sign-in clicked (wire to your OAuth endpoint).");
    });

    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      msgError.style.display = "none";
      msgOk.style.display = "none";

      const email = document.getElementById("email").value.trim();
      const password = pw.value;

      if (!email || !password) return showError("Please enter email and password.");
      if (password.length < 6) return showError("Password must be at least 6 characters.");

      btnLogin.disabled = true;
      btnLogin.classList.add("loading");

      try{
		const endpoint = isRegisterMode ? REGISTER_ENDPOINT : LOGIN_ENDPOINT;
        const res = await fetch(endpoint, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            email,
            password,
            remember: document.getElementById("remember").checked ? 1 : 0
          })
        });

        const text = await res.text();
        let json;
        try { json = JSON.parse(text); } catch { json = null; }

        if (!res.ok){
          const msg = (json && (json.message || json.error)) ? (json.message || json.error) : (text || "Login failed.");
          return showError(msg);
        }

        if (json && json.success){
          showOk("Signed in! Redirecting…");
          const redirectTo = json.redirect || "/dashboard";
          setTimeout(() => location.href = redirectTo, 600);
        } else {
          showError((json && (json.message || json.error)) ? (json.message || json.error) : "Unexpected response.");
        }

      } catch(err){
        showError("Network error. Check your connection and try again.");
      } finally {
        btnLogin.disabled = false;
        btnLogin.classList.remove("loading");
      }
    });
	
	// ---- Register mode toggle ----
	let isRegisterMode = false;

	const titleEl = document.querySelector(".card h2");
	const subEl = document.querySelector(".sub");
	const createLink = document.getElementById("createLink");

	createLink.addEventListener("click", (e) => {
  	e.preventDefault();

  	isRegisterMode = !isRegisterMode;

  	msgError.style.display = "none";
  	msgOk.style.display = "none";

  	if (isRegisterMode) {
    	titleEl.textContent = "Create Account";
    	subEl.textContent = "Create a new account to enter the portal.";
    	btnLogin.querySelector(".btn-text").textContent = "Create Account";
    	createLink.textContent = "Already have an account?";
  	} else {
    	titleEl.textContent = "Portal Login";
    	subEl.textContent = "Use your email and password, or continue with Google.";
    	btnLogin.querySelector(".btn-text").textContent = "Enter Portal";
    	createLink.textContent = "Don’t have an account? Create one";
  	}
	});
  </script>
</body>
</html>
