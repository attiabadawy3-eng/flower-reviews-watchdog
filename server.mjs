
import express from "express";
import crypto from "node:crypto";
import {
  generateRegistrationOptions,
  verifyRegistrationResponse,
  generateAuthenticationOptions,
  verifyAuthenticationResponse,
} from "@simplewebauthn/server";

const app = express();
app.disable("x-powered-by");
app.use(express.json({ limit: "1mb" }));

const PORT = Number(process.env.PORT || 10000);
const RP_ID = String(process.env.RP_ID || "").trim();
const ORIGIN = String(process.env.ORIGIN || "").trim().replace(/\/$/, "");
const PAIR_CODE = String(process.env.PAIR_CODE || "").trim();
const BRIDGE_KEY = String(process.env.BRIDGE_KEY || "").trim();
const PROOF_SECRET = String(process.env.PROOF_SECRET || "").trim();

if (!RP_ID || !ORIGIN || !PAIR_CODE || !BRIDGE_KEY || !PROOF_SECRET) {
  throw new Error("Missing required environment variables.");
}

const state = {
  owner: null,
  registerChallenge: null,
  requests: new Map(),
  tokenToRequest: new Map(),
};

const b64 = (buf) => Buffer.from(buf).toString("base64url");
const unb64 = (s) => Buffer.from(String(s || ""), "base64url");
const safeText = (v, max = 400) => String(v ?? "").replace(/[\u0000-\u001f\u007f]/g, " ").trim().slice(0, max);
const timingSafeEqualText = (a, b) => {
  const aa = Buffer.from(String(a));
  const bb = Buffer.from(String(b));
  return aa.length === bb.length && crypto.timingSafeEqual(aa, bb);
};
const parseCookies = (req) => Object.fromEntries(
  String(req.headers.cookie || "").split(";").map(x => x.trim()).filter(Boolean).map(x => {
    const i = x.indexOf("=");
    return i < 0 ? [x, ""] : [x.slice(0, i), decodeURIComponent(x.slice(i + 1))];
  })
);
const bindingFromRequest = (req) => {
  const cookieToken = parseCookies(req).sara_mobile_binding;
  const bodyToken = req.body?.bindingToken;
  return cookieToken || bodyToken || "";
};
const setBindingCookie = (res, token) => {
  res.setHeader("Set-Cookie", "sara_mobile_binding=" + encodeURIComponent(token) + "; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=31536000");
};
const authBridge = (req, res, next) => {
  const h = req.headers.authorization || "";
  if (!h.startsWith("Bearer ")) return res.status(401).json({ error: "unauthorized" });
  if (!timingSafeEqualText(h.slice(7), BRIDGE_KEY)) return res.status(401).json({ error: "unauthorized" });
  next();
};
const hmac = (payload) =>
  crypto.createHmac("sha256", PROOF_SECRET).update(JSON.stringify(payload)).digest("base64url");
const signProof = (payload) => hmac(payload);
const issueBindingToken = (credential) => {
  const payload = {
    version: "SARA_MOBILE_BINDING_V1",
    credential: serializeCredential(credential),
    issuedAt: new Date().toISOString(),
  };
  const body = Buffer.from(JSON.stringify(payload)).toString("base64url");
  const sig = hmac(payload);
  return body + "." + sig;
};
const readBindingToken = (token) => {
  const [body, sig] = String(token || "").split(".");
  if (!body || !sig) throw new Error("bad_binding_token");
  const payload = JSON.parse(Buffer.from(body, "base64url").toString("utf8"));
  if (!payload || payload.version !== "SARA_MOBILE_BINDING_V1" || !payload.credential) throw new Error("bad_binding_payload");
  const expected = hmac(payload);
  if (!timingSafeEqualText(sig, expected)) throw new Error("bad_binding_signature");
  return payload;
};
const serializeCredential = (c) => ({
  id: c.id,
  publicKey: b64(c.publicKey),
  counter: c.counter,
  transports: c.transports || [],
});
const hydrateCredential = (c) => ({
  id: c.id,
  publicKey: unb64(c.publicKey),
  counter: Number(c.counter || 0),
  transports: Array.isArray(c.transports) ? c.transports : [],
});

app.get("/health", (_req, res) => {
  res.json({
    ok: true,
    service: "sara-mobile-approval-gateway",
    staging: true,
    pairingModel: "browser-held-signed-binding",
    pending: [...state.requests.values()].filter((x) => x.status === "pending").length,
  });
});

app.get("/", (_req, res) => {
  res.type("html").send(
    '<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Sara Mobile Approval</title><style>' +
    'body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#f5f6f8;color:#171717;margin:0}.wrap{max-width:560px;margin:0 auto;padding:28px 18px}.card{background:white;border:1px solid #e6e6e6;border-radius:18px;padding:24px;box-shadow:0 8px 30px #0000000d}h1{font-size:24px;margin:0 0 10px}.muted{color:#666;line-height:1.6}a{display:inline-block;margin-top:16px;color:#111;font-weight:700}</style></head><body>' +
    '<div class="wrap"><div class="card"><h1>موافقات سارة من الموبايل</h1><div class="muted">بوابة Staging آمنة للموافقة عبر Passkey / Face ID. لا تنفذ أي عملية مالية مباشرة.</div><a href="/pair">ربط الآيفون</a></div></div></body></html>'
  );
});

app.get("/pair", (_req, res) => {
  res.type("html").send(
    '<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>ربط الآيفون</title><style>' +
    'body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#f5f6f8;margin:0;color:#171717}.wrap{max-width:560px;margin:auto;padding:24px 18px}.card{background:#fff;border:1px solid #e5e5e5;border-radius:18px;padding:24px}input,button{font:inherit;width:100%;box-sizing:border-box;padding:14px;border-radius:12px}.code{border:1px solid #ccc;margin:12px 0}.btn{border:0;background:#111;color:#fff;font-weight:700}.msg{margin-top:14px;white-space:pre-wrap;color:#555}</style></head><body>' +
    '<div class="wrap"><div class="card"><h2>ربط Passkey على الآيفون</h2><p>اكتب كود الربط ثم وافق بـFace ID.</p><input id="code" class="code" inputmode="numeric" autocomplete="one-time-code" placeholder="كود الربط"><button id="go" class="btn">ربط الآيفون</button><div id="msg" class="msg"></div></div></div>' +
    '<script type="module">import{startRegistration}from"https://cdn.jsdelivr.net/npm/@simplewebauthn/browser@13/+esm";const msg=document.getElementById("msg"),btn=document.getElementById("go"),code=document.getElementById("code");btn.onclick=async()=>{btn.disabled=true;msg.textContent="جاري التجهيز...";try{const c=code.value.trim();const o=await fetch("/api/register/options",{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify({code:c})});const j=await o.json();if(!o.ok)throw new Error(j.error||"registration options failed");const response=await startRegistration({optionsJSON:j.options});const v=await fetch("/api/register/verify",{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify({code:c,response})});const x=await v.json();if(!v.ok)throw new Error(x.error||"registration failed");msg.textContent="تم ربط الآيفون بنجاح."}catch(e){msg.textContent="فشل الربط: "+e.message}finally{btn.disabled=false}};</script></body></html>'
  );
});

app.post("/api/register/options", async (req, res) => {
  if (state.owner) return res.status(409).json({ error: "already_paired" });
  if (!timingSafeEqualText(req.body?.code || "", PAIR_CODE)) return res.status(403).json({ error: "bad_pair_code" });
  const options = await generateRegistrationOptions({
    rpName: "Sara Mobile Approval",
    rpID: RP_ID,
    userName: "Attia",
    userDisplayName: "Attia",
    attestationType: "none",
    authenticatorSelection: { residentKey: "required", userVerification: "required" },
  });
  state.registerChallenge = options.challenge;
  res.json({ options });
});

app.post("/api/register/verify", async (req, res) => {
  if (state.owner) return res.status(409).json({ error: "already_paired" });
  if (!timingSafeEqualText(req.body?.code || "", PAIR_CODE)) return res.status(403).json({ error: "bad_pair_code" });
  if (!state.registerChallenge) return res.status(409).json({ error: "no_registration_challenge" });
  const verification = await verifyRegistrationResponse({
    response: req.body?.response,
    expectedChallenge: state.registerChallenge,
    expectedOrigin: ORIGIN,
    expectedRPID: RP_ID,
    requireUserVerification: true,
  });
  if (!verification.verified || !verification.registrationInfo) {
    return res.status(400).json({ error: "registration_not_verified" });
  }
  const credential = verification.registrationInfo.credential;
  const bindingToken = issueBindingToken(credential);
  state.registerChallenge = null;
  setBindingCookie(res, bindingToken);
  res.json({ ok: true, paired: true, credentialId: credential.id });
});

app.post("/api/bridge/request", authBridge, (req, res) => {
  const requestId = safeText(req.body?.requestId, 120);
  const effectHash = safeText(req.body?.effectHash, 128);
  const nonce = safeText(req.body?.nonce, 200);
  const summary = safeText(req.body?.summary, 500);
  const expiresAt = String(req.body?.expiresAt || "");
  const exp = Date.parse(expiresAt);
  if (!requestId || !effectHash || !nonce || !Number.isFinite(exp) || exp <= Date.now()) {
    return res.status(400).json({ error: "invalid_request" });
  }
  if (state.requests.has(requestId)) return res.status(409).json({ error: "duplicate_request_id" });
  const token = crypto.randomBytes(24).toString("base64url");
  const row = {
    requestId, effectHash, nonce, summary, expiresAt, token,
    status: "pending", authChallenge: null, proof: null,
    createdAt: new Date().toISOString(),
  };
  state.requests.set(requestId, row);
  state.tokenToRequest.set(token, requestId);
  res.json({ ok: true, requestId, approvalUrl: ORIGIN + "/a/" + token });
});

app.get("/api/approval/view/:token", (req, res) => {
  const requestId = state.tokenToRequest.get(req.params.token);
  const row = requestId ? state.requests.get(requestId) : null;
  if (!row) return res.status(404).json({ error: "not_found" });
  res.json({ requestId: row.requestId, summary: row.summary, expiresAt: row.expiresAt, status: row.status });
});



app.get("/staging/controlplane-test", (_req, res) => {
  const requestId = "cpdry-" + crypto.randomUUID();
  const nonce = crypto.randomBytes(32).toString("base64url");
  const effectHash = crypto.createHash("sha256")
    .update(JSON.stringify({ type: "staging.controlplane.dryrun", amount: 0, execution: false }))
    .digest("hex")
    .toUpperCase();
  const token = crypto.randomBytes(24).toString("base64url");
  const row = {
    requestId,
    effectHash,
    nonce,
    summary: "اختبار Control Plane Dry-run — لا يوجد أي تنفيذ مالي",
    expiresAt: new Date(Date.now() + 10 * 60 * 1000).toISOString(),
    token,
    status: "pending",
    authChallenge: null,
    proof: null,
    createdAt: new Date().toISOString(),
    controlPlaneStaging: true,
  };
  state.requests.set(requestId, row);
  state.tokenToRequest.set(token, requestId);
  console.log("CP_DRYRUN_ENVELOPE", JSON.stringify({
    requestId: row.requestId,
    effectHash: row.effectHash,
    nonce: row.nonce,
    expiresAt: row.expiresAt
  }));
  res.redirect(302, "/a/" + token);
});

app.get("/a/:token", (_req, res) => {
  res.type("html").send(
    '<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>موافقة سارة</title><style>' +
    'body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#f5f6f8;margin:0;color:#171717}.wrap{max-width:560px;margin:auto;padding:24px 18px}.card{background:#fff;border:1px solid #e5e5e5;border-radius:18px;padding:24px}.summary{font-size:19px;line-height:1.7;margin:18px 0;padding:16px;background:#f7f7f7;border-radius:12px}.row{display:grid;grid-template-columns:1fr 1fr;gap:10px}button{font:inherit;padding:14px;border-radius:12px;border:0;font-weight:700}.ok{background:#111;color:#fff}.no{background:#eee}.msg{margin-top:14px;color:#555;white-space:pre-wrap}</style></head><body>' +
    '<div class="wrap"><div class="card"><h2>طلب موافقة</h2><div class="summary" id="summary">جاري تحميل الطلب...</div><div class="row"><button class="ok" id="approve">موافقة بـFace ID</button><button class="no" id="reject">رفض بـFace ID</button></div><div class="msg" id="msg"></div></div></div>' +
    '<script type="module">import{startAuthentication}from"https://cdn.jsdelivr.net/npm/@simplewebauthn/browser@13/+esm";const token=location.pathname.split("/").pop(),msg=document.getElementById("msg"),summary=document.getElementById("summary");let view=null;async function load(){const r=await fetch("/api/approval/view/"+encodeURIComponent(token));view=await r.json();if(!r.ok){summary.textContent="الطلب غير موجود";return}summary.textContent=view.summary||"طلب موافقة من سارة";if(Date.parse(view.expiresAt)<=Date.now())msg.textContent="انتهت صلاحية الطلب."}await load();async function act(decision){if(!view||Date.parse(view.expiresAt)<=Date.now())return;try{const o=await fetch("/api/approval/options",{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify({token,decision})});const j=await o.json();if(!o.ok)throw new Error(j.error||"options failed");const response=await startAuthentication({optionsJSON:j.options});const v=await fetch("/api/approval/verify",{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify({token,decision,response})});const x=await v.json();if(!v.ok)throw new Error(x.error||"verification failed");msg.textContent=decision==="approve"?"تمت الموافقة بنجاح.":"تم الرفض بنجاح."}catch(e){msg.textContent="تعذر إكمال الطلب: "+e.message}}document.getElementById("approve").onclick=()=>act("approve");document.getElementById("reject").onclick=()=>act("reject");</script></body></html>'
  );
});

app.post("/api/approval/options", async (req, res) => {
  let binding;
  try { binding = readBindingToken(bindingFromRequest(req)); }
  catch { return res.status(409).json({ error: "not_paired" }); }
  const requestId = state.tokenToRequest.get(String(req.body?.token || ""));
  const row = requestId ? state.requests.get(requestId) : null;
  if (!row) return res.status(404).json({ error: "request_not_found" });
  if (row.status !== "pending") return res.status(409).json({ error: "request_already_decided" });
  if (Date.parse(row.expiresAt) <= Date.now()) return res.status(410).json({ error: "request_expired" });
  const owner = hydrateCredential(binding.credential);
  const options = await generateAuthenticationOptions({
    rpID: RP_ID,
    userVerification: "required",
    allowCredentials: [{ id: owner.id, transports: owner.transports }],
  });
  row.authChallenge = options.challenge;
  res.json({ options });
});

app.post("/api/approval/verify", async (req, res) => {
  let binding;
  try { binding = readBindingToken(bindingFromRequest(req)); }
  catch { return res.status(409).json({ error: "not_paired" }); }
  const token = String(req.body?.token || "");
  const requestId = state.tokenToRequest.get(token);
  const row = requestId ? state.requests.get(requestId) : null;
  if (!row) return res.status(404).json({ error: "request_not_found" });
  if (row.status !== "pending") return res.status(409).json({ error: "request_already_decided" });
  if (Date.parse(row.expiresAt) <= Date.now()) return res.status(410).json({ error: "request_expired" });
  const decision = req.body?.decision === "reject" ? "rejected" : "approved";
  const owner = hydrateCredential(binding.credential);
  const verification = await verifyAuthenticationResponse({
    response: req.body?.response,
    expectedChallenge: row.authChallenge,
    expectedOrigin: ORIGIN,
    expectedRPID: RP_ID,
    credential: owner,
    requireUserVerification: true,
  });
  if (!verification.verified) return res.status(400).json({ error: "authentication_not_verified" });
  const updatedCredential = { ...owner, counter: verification.authenticationInfo.newCounter };
  const proofPayload = {
    version: "SARA_MOBILE_PROOF_V1",
    requestId: row.requestId,
    effectHash: row.effectHash,
    nonce: row.nonce,
    decision,
    credentialId: owner.id,
    verifiedAt: new Date().toISOString(),
  };
  row.status = decision;
  row.proof = { ...proofPayload, signature: signProof(proofPayload) };
  row.authChallenge = null;
  if (row.controlPlaneStaging) {
    console.log("CP_DRYRUN_PROOF", JSON.stringify(row.proof));
  }
  console.log("MOBILE_APPROVAL_DECIDED", JSON.stringify({ requestId: row.requestId, status: row.status, verifiedAt: proofPayload.verifiedAt, staging: row.requestId.startsWith("staging-") || row.requestId.startsWith("cpdry-") }));
  setBindingCookie(res, issueBindingToken(updatedCredential));
  res.json({ ok: true, status: row.status });
});

app.get("/api/bridge/result/:requestId", authBridge, (req, res) => {
  const row = state.requests.get(req.params.requestId);
  if (!row) return res.status(404).json({ error: "not_found" });
  res.json({
    ok: true,
    requestId: row.requestId,
    status: row.status,
    expiresAt: row.expiresAt,
    proof: row.proof || null,
  });
});

app.listen(PORT, "0.0.0.0", () => {
  console.log("Sara Mobile Approval gateway listening on port", PORT);
});
