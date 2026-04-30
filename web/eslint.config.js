import js from "@eslint/js";
import vue from "eslint-plugin-vue";
import tsConfig from "@vue/eslint-config-typescript";
import prettierConfig from "@vue/eslint-config-prettier";
import globals from "globals";

export default [
  {
    ignores: ["dist/", "node_modules/", "src/assets/methodology.md", "public/data/"],
  },
  js.configs.recommended,
  ...vue.configs["flat/recommended"],
  ...tsConfig(),
  prettierConfig,
  {
    rules: {
      "vue/multi-word-component-names": "off",
    },
  },
  {
    files: ["scripts/**/*.mjs"],
    languageOptions: {
      globals: { ...globals.node },
      sourceType: "module",
    },
    rules: {
      "@typescript-eslint/no-require-imports": "off",
    },
  },
];
