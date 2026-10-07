// Issues SARA_MOBILE_PROOF_V2 only after a WebAuthn assertion that the server
// itself verified WITH user verification (Face ID / passcode). The Ed25519 private
// key lives only here; Sara Bridge holds the public key.

import crypto from 'node:crypto';

export const PROOF_VERSION = 'SARA_MOBILE_PROOF_V2';

export function loadProofPrivateKey({ pem, path, readFileSync } = {}) {
  let text = String(pem || '').replace(/\\n/g, '\n').trim();
  if (!text && path) text = String(readFileSync(path, 'utf8')).trim();
  if (!text) throw new Error('proof_signing_key_missing');
  const key = crypto.createPrivateKey(text);
  if (key.asymmetricKeyType !== 'ed25519') throw new Error('proof_signing_key_not_ed25519');
  return key;
}

/** Canonical signed payload. Key order must match the Bridge verifier exactly. */
export function canonicalProof(p) {
  return {
    version: p.version,
    alg: p.alg,
    requestId: p.requestId,
    effectHash: p.effectHash,
    nonce: p.nonce,
    decision: p.decision,
    credentialId: p.credentialId,
    userVerified: p.userVerified,
    verifiedAt: p.verifiedAt,
  };
}

/**
 * @param verification  result of @simplewebauthn/server verifyAuthenticationResponse
 * @param row           the pending request {requestId, effectHash, nonce}
 */
export function issueMobileProof({ verification, row, credentialId, decision, privateKey, now = Date.now() }) {
  if (!privateKey) throw new Error('proof_signing_key_missing');
  if (verification?.verified !== true) throw new Error('authentication_not_verified');
  if (verification?.authenticationInfo?.userVerified !== true) throw new Error('user_verification_missing');
  if (!row?.requestId || !row?.effectHash || !row?.nonce) throw new Error('request_binding_missing');
  if (decision !== 'approved' && decision !== 'rejected') throw new Error('bad_decision');
  if (!credentialId) throw new Error('credential_missing');
  const proof = canonicalProof({
    version: PROOF_VERSION, alg: 'Ed25519',
    requestId: row.requestId, effectHash: row.effectHash, nonce: row.nonce,
    decision, credentialId: String(credentialId), userVerified: true,
    verifiedAt: new Date(now).toISOString(),
  });
  const signature = crypto.sign(null, Buffer.from(JSON.stringify(proof)), privateKey).toString('base64url');
  return { proof, signature };
}
