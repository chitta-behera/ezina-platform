import config from "@ezina/config/eslint/next";

// A component library has no pages directory.
export default [...config, { rules: { "@next/next/no-html-link-for-pages": "off" } }];
