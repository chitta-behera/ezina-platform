// Shared flat ESLint config for Next.js apps in this workspace.
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const config = [
  ...nextVitals,
  ...nextTs,
  { ignores: [".next/**", "out/**", "next-env.d.ts"] },
  {
    // Static export (output: "export") serves images as-is; plain <img> with width/height is intended.
    rules: { "@next/next/no-img-element": "off" },
  },
];

export default config;
