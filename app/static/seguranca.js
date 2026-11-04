/* Verificação de segurança: resolve um desafio curto no navegador e volta para o site. */
// SHA-256 de uma mensagem curta (até 55 bytes, um bloco): devolve a primeira palavra (32 bits).
const K = new Uint32Array([0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2]);
const W = new Uint32Array(64);
function firstWord(str) {
  const n = str.length;
  W.fill(0, 0, 16);
  for (let i = 0; i < n; i++) W[i >> 2] |= (str.charCodeAt(i) & 0xff) << (24 - (i % 4) * 8);
  W[n >> 2] |= 0x80 << (24 - (n % 4) * 8);
  W[15] = n * 8;
  for (let i = 16; i < 64; i++) {
    const a = W[i - 15], b = W[i - 2];
    const s0 = ((a >>> 7) | (a << 25)) ^ ((a >>> 18) | (a << 14)) ^ (a >>> 3);
    const s1 = ((b >>> 17) | (b << 15)) ^ ((b >>> 19) | (b << 13)) ^ (b >>> 10);
    W[i] = (W[i - 16] + s0 + W[i - 7] + s1) | 0;
  }
  let a = 0x6a09e667, b = 0xbb67ae85, c = 0x3c6ef372, d = 0xa54ff53a, e = 0x510e527f, f = 0x9b05688c, g = 0x1f83d9ab, h = 0x5be0cd19;
  for (let i = 0; i < 64; i++) {
    const S1 = ((e >>> 6) | (e << 26)) ^ ((e >>> 11) | (e << 21)) ^ ((e >>> 25) | (e << 7));
    const t1 = (h + S1 + ((e & f) ^ (~e & g)) + K[i] + W[i]) | 0;
    const S0 = ((a >>> 2) | (a << 30)) ^ ((a >>> 13) | (a << 19)) ^ ((a >>> 22) | (a << 10));
    const t2 = (S0 + ((a & b) ^ (a & c) ^ (b & c))) | 0;
    h = g; g = f; f = e; e = (d + t1) | 0; d = c; c = b; b = a; a = (t1 + t2) | 0;
  }
  return (a + 0x6a09e667) >>> 0;
}
const button = document.getElementById("check");
const label = document.getElementById("label");
const bar = document.getElementById("bar");
const statusEl = document.getElementById("status");
const back = (() => {
  const v = new URLSearchParams(location.search).get("volta") || "/";
  // Só endereços do próprio site: "//outro.com" e "/\\outro.com" levariam para fora.
  return /^\/(?![\/\\])/.test(v) && !/[\\\s]/.test(v) ? v : "/";
})();

function solve(salt, bits, onProgress) {
  return new Promise((resolve) => {
    const shift = 32 - bits, expected = 2 ** bits;
    let n = 0;
    const step = () => {
      const end = n + 50000;
      for (; n < end; n++) {
        if ((firstWord(salt + ":" + n) >>> shift) === 0) return resolve(String(n));
      }
      onProgress(Math.min(0.95, 1 - Math.exp(-n / expected)));
      setTimeout(step, 0);
    };
    step();
  });
}

const barWrap = document.getElementById("bar-wrap");

// Foto da capa e WhatsApp do buffet: deixam a página com a cara do site e dão uma saída
// para quem não conseguir passar (a pessoa nunca fica sem como falar com o buffet).
fetch("/_seguranca/contato", { cache: "no-store" })
  .then((r) => (r.ok ? r.json() : null))
  .then((info) => {
    if (!info) return;
    if (info.whatsapp) {
      document.getElementById("help-link").href = info.whatsapp;
      document.getElementById("help").hidden = false;
    }
    if (info.cover) {
      const photo = new Image();
      photo.onload = () => {
        const backdrop = document.getElementById("backdrop");
        backdrop.style.backgroundImage = `url("${info.cover}")`;
        backdrop.classList.add("is-on");
      };
      photo.src = info.cover;
    }
  })
  .catch(() => {});

async function run() {
  button.disabled = true;
  button.className = "check is-working";
  label.textContent = "Confirmando…";
  statusEl.textContent = "";
  statusEl.classList.remove("is-ok");
  barWrap.hidden = false;
  bar.style.width = "4%";
  try {
    const challenge = await (await fetch("/_seguranca/desafio", { cache: "no-store" })).json();
    const nonce = await solve(challenge.salt, challenge.bits, (p) => { bar.style.width = `${Math.round(p * 100)}%`; });
    const response = await fetch("/_seguranca/verificar", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token: challenge.token, nonce }),
    });
    if (!response.ok) throw new Error("recusado");
    bar.style.width = "100%";
    button.className = "check is-done";
    label.textContent = "Confirmado";
    statusEl.textContent = "Tudo certo! Abrindo o site…";
    statusEl.classList.add("is-ok");
    setTimeout(() => location.replace(back), 700);
  } catch {
    bar.style.width = "0";
    barWrap.hidden = true;
    button.className = "check";
    button.disabled = false;
    label.textContent = "Tentar de novo";
    statusEl.textContent = "Não foi possível confirmar. Confira a internet e tente de novo.";
  }
}
button.addEventListener("click", run);
