let panel;

function create() {
  injectThemeStyles();
  panel = document.createElement("div");
  panel.id = "text_div";
  panel.innerHTML =
    "<p>Congratulations! You just created your first plugin.</p>";
  return panel;
}

function injectThemeStyles() {
  if (document.getElementById("udt-theme-styles")) return;
  const style = document.createElement("style");
  style.id = "udt-theme-styles";
  style.textContent = `
        #text_div {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            padding: 24px;
            margin: 0;
            box-sizing: border-box;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
        }
        
        #text_div p {
            margin: 0;
            font-size: 18px;
            line-height: 1.6;
            text-align: center;
            max-width: 600px;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
        }
        
        #text_div.theme-dark {
            background: linear-gradient(135deg, #1a1a1a 0%, #2d2d2d 100%);
            color: #ffffff;
        }
        
        #text_div.theme-dark p {
            background-color: rgba(255, 255, 255, 0.05);
            color: #e0e0e0;
            box-shadow: 0 2px 12px rgba(0, 0, 0, 0.3);
            border: 1px solid rgba(255, 255, 255, 0.1);
        }
        
        #text_div.theme-light {
            background: linear-gradient(135deg, #f5f5f5 0%, #ffffff 100%);
            color: #000000;
        }
        
        #text_div.theme-light p {
            background-color: #ffffff;
            color: #333333;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
            border: 1px solid rgba(0, 0, 0, 0.05);
        }
`;
  document.head.appendChild(style);
}

function updateTheme(theme) {
  const isDark = theme.includes("dark");
  // Toggle theme classes on body
  panel.classList.toggle("theme-dark", isDark);
  panel.classList.toggle("theme-light", !isDark);
}

document.theme.onUpdated.addListener((theme) => {
  updateTheme(theme);
});

function show(rootNode) {
  rootNode.appendChild(create());
  let currentTheme = document.theme.getCurrent();
  updateTheme(currentTheme);
}

require('uxp').entrypoints.setup({
  panels: {
    samplePlugin: {
      show,
    },
  },
  commands: {
    show_alert: {
      run: async (event) => {
        alert('This is an alert message');
        console.log('Show alert command triggered', event);
        // Your command implementation here
        return "Alert shown successfully!";
      },
      cancel: async (event) => {
        console.log('Command cancelled', event);
      },
    },
  },
});
