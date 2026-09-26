// ES3 gate for ExtendScript (AGENTS.md §7.1): modern syntax must fail the
// build, not the review. ecmaVersion 3 rejects let/const/arrows/templates
// at parse time; no-restricted-syntax bans modern runtime idioms that still
// parse (Array extras, promises, fetch); no-undef with declared globals
// catches Node/browser-isms. Only panel/host is linted — panel/www is
// modern Chromium by design (§7.2).
import globals from "globals";

export default [
  {
    files: ["panel/host/*.jsx"],
    languageOptions: {
      ecmaVersion: 3,
      sourceType: "script",
      globals: {
        ...globals.es3,
        $: "readonly",
        app: "readonly",
        FootageItem: "readonly",
        FileSource: "readonly",
        CompItem: "readonly",
        ImportOptions: "readonly",
        File: "readonly",
        Folder: "readonly",
        JSON: "readonly",
        alert: "readonly",
      },
    },
    rules: {
      "no-restricted-syntax": [
        "error",
        {
          selector: "CallExpression[callee.type='MemberExpression'][callee.property.name=/^(map|forEach|filter|reduce|find|some|every)$/]",
          message: "ES3 host: use for loops (Array extras are forbidden in host.jsx).",
        },
        {
          selector: "Identifier[name=/^(Promise|fetch|console)$/]",
          message: "ES3 host: no promises/fetch/console — JSON in/out only.",
        },
      ],
    },
  },
];
