const C = {
  reset: "\x1b[0m", dim: "\x1b[2m", red: "\x1b[31m",
  green: "\x1b[32m", yellow: "\x1b[33m", cyan: "\x1b[36m",
};

const stamp = () => new Date().toISOString().slice(11, 19);

export const log = {
  step: (m) => console.log(`${C.cyan}▸${C.reset} ${m}`),
  info: (m) => console.log(`${C.dim}${stamp()}${C.reset} ${m}`),
  ok: (m) => console.log(`${C.green}✓${C.reset} ${m}`),
  warn: (m) => console.warn(`${C.yellow}!${C.reset} ${m}`),
  error: (m) => console.error(`${C.red}✗${C.reset} ${m}`),
};
