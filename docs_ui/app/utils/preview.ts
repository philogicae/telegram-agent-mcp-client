export const CUSTOM_CSS = `
          /* General Typography */
          p, li {
            line-height: 1.6;
            margin-bottom: 1rem;
          }

          /* Headings */
          h1, h2, h3, h4, h5, h6 {
            font-family: sans-serif;
            font-weight: 600;
            margin-bottom: 1rem;
            line-height: 1.25;
          }
          h1 { 
            font-size: 2.2rem; 
            padding-bottom: 0.5rem;
            margin-bottom: 1.5rem;
            border-bottom: 1px solid #a2a9b1;
          }
          h2 { 
            font-size: 1.8rem; 
            margin-top: 2rem;
            padding-bottom: 0.25rem;
            border-bottom: 1px solid #a2a9b1;
          }
          h3 {
            font-size: 1.5rem;
            margin-top: 2rem;
            font-weight: bold;
          }
          h4 { font-size: 1.2rem; margin-top: 1.5rem; }

          /* Lists */
          ul, ol {
            margin-bottom: 1rem;
            padding-left: 2em;
          }
          ul { list-style-type: disc; }
          ol { list-style-type: decimal; }
          li { margin-bottom: 0.5rem; }

          /* Links */
          a {
            color: #0645ad;
            text-decoration: none;
          }
          .dark a { color: #6891d4; }
          a:visited { color: #0b0080; }
          .dark a:visited { color: #a395e9; }
          a:hover { text-decoration: underline; }

          /* Media */
          img {
            margin: 1rem 0;
            max-width: 100%;
            height: auto;
            max-height: 300px;
            border: 1px solid #eaecf0;
            padding: 4px;
            border-radius: 0.25rem;
          }

          /* Hidden Elements */
          blockquote, .report-id, #report-id {
            display: none;
          }
        `
