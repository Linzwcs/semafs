import { defineConfig } from 'vitepress'
import { withMermaid } from 'vitepress-plugin-mermaid'

export default withMermaid(
  defineConfig({
    title: 'SemaFS',
    description: 'Semantic Filesystem for LLM Memory',

    head: [
      ['style', {}, `
        :root {
          --vp-home-hero-name-color: transparent;
          --vp-home-hero-name-background: -webkit-linear-gradient(120deg, #3eaf7c 30%, #42b983);
          --vp-home-hero-image-background-image: linear-gradient(-45deg, #3eaf7c50 50%, #42b98350 50%);
          --vp-home-hero-image-filter: blur(40px);
        }
      `],
      ['link', { rel: 'icon', href: '/logo.svg' }],
      ['meta', { name: 'theme-color', content: '#3eaf7c' }],
      ['meta', { name: 'og:type', content: 'website' }],
      ['meta', { name: 'og:title', content: 'SemaFS - Semantic Filesystem for LLM Memory' }],
      ['meta', { name: 'og:description', content: 'Give your LLM a persistent, self-organizing memory that grows smarter over time.' }],
    ],

    themeConfig: {
      logo: '/logo.svg',

      nav: [
        { text: 'Guide', link: '/guide/introduction' },
        { text: 'API', link: '/api/semafs' },
        { text: 'Design', link: '/design/architecture' },
        {
          text: 'Resources',
          items: [
            { text: 'Paper', link: '/paper' },
            { text: 'Changelog', link: 'https://github.com/linzwcs/semafs/releases' }
          ]
        }
      ],

      sidebar: {
        '/guide/': [
          {
            text: 'Getting Started',
            items: [
              { text: 'Introduction', link: '/guide/introduction' },
              { text: 'Value & Benchmark', link: '/guide/value-benchmark' },
              { text: 'Quick Start', link: '/guide/quickstart' },
              { text: 'Core Concepts', link: '/guide/concepts' },
            ]
          },
          {
            text: 'Usage',
            items: [
              { text: 'Writing Memories', link: '/guide/writing' },
              { text: 'Reading & Querying', link: '/guide/reading' },
              { text: 'Maintenance', link: '/guide/maintenance' },
              { text: 'LLM Integration', link: '/guide/llm-integration' },
              { text: 'Agent Memory', link: '/guide/agent-memory' },
            ]
          },
          {
            text: 'Advanced',
            items: [
              { text: 'Tree Operations', link: '/guide/operations' },
              { text: 'Strategies', link: '/guide/strategies' },
              { text: 'Transactions', link: '/guide/transactions' },
            ]
          }
        ],
        '/api/': [
          {
            text: 'API Reference',
            items: [
              { text: 'SemaFS', link: '/api/semafs' },
              { text: 'TreeNode', link: '/api/node' },
              { text: 'Operations', link: '/api/operations' },
              { text: 'Views', link: '/api/views' },
              { text: 'Strategy', link: '/api/strategy' },
              { text: 'Repository', link: '/api/repository' },
            ]
          }
        ],
        '/design/': [
          {
            text: 'System Design',
            items: [
              { text: 'Design Philosophy', link: '/design/philosophy' },
              { text: 'ADR Records', link: '/design/adr' },
              { text: 'Architecture', link: '/design/architecture' },
              { text: 'Data Model', link: '/design/data-model' },
              { text: 'Maintenance System', link: '/design/maintenance' },
              { text: 'Transaction Model', link: '/design/transactions' },
              { text: 'Evolution Roadmap', link: '/design/evolution' },
            ]
          }
        ]
      },

      socialLinks: [
        { icon: 'github', link: 'https://github.com/linzwcs/semafs' }
      ],

      footer: {
        message: 'Released under the MIT License.',
        copyright: 'Copyright © 2024-present'
      },

      search: {
        provider: 'local'
      },

      editLink: {
        pattern: 'https://github.com/linzwcs/semafs/edit/main/docs/:path',
        text: 'Edit this page on GitHub'
      }
    },

    markdown: {
      lineNumbers: true
    }
  })
)
