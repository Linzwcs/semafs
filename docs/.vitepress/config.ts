import { defineConfig } from 'vitepress'
import { withMermaid } from 'vitepress-plugin-mermaid'

export default withMermaid(
  defineConfig({
    title: 'SemaFS',
    description: 'Semantic Filesystem for LLM Memory',
    base: '/semafs/',

    head: [
      ['link', { rel: 'icon', href: '/logo.svg' }],
      ['meta', { name: 'theme-color', content: '#0d9488' }],
      ['meta', { name: 'og:type', content: 'website' }],
      ['meta', { name: 'og:title', content: 'SemaFS Documentation' }],
      [
        'meta',
        {
          name: 'og:description',
          content:
            'Architecture-first documentation for SemaFS: semantic tree memory with event-driven maintenance.',
        },
      ],
      [
        'style',
        {},
        `
        :root {
          --vp-c-brand-1: #0d9488;
          --vp-c-brand-2: #0f766e;
          --vp-c-brand-3: #115e59;
          --vp-home-hero-name-color: transparent;
          --vp-home-hero-name-background: -webkit-linear-gradient(120deg, #0d9488 30%, #14b8a6);
        }
      `,
      ],
    ],

    themeConfig: {
      logo: '/logo.svg',

      nav: [
        { text: 'Guide', link: '/guide/introduction' },
        { text: 'Architecture', link: '/design/architecture' },
        { text: 'API Reference', link: '/api/semafs' },
        {
          text: 'Resources',
          items: [
            { text: 'GitHub', link: 'https://github.com/linzwcs/semafs' },
            { text: 'Development History', link: '/dev_history/semafs_v2_architecture' },
          ],
        },
      ],

      sidebar: {
        '/guide/': [
          {
            text: 'Getting Started',
            items: [
              { text: 'Introduction', link: '/guide/introduction' },
              { text: 'Quick Start', link: '/guide/quickstart' },
              { text: 'Value and Limits', link: '/guide/value-benchmark' },
              { text: 'Core Concepts', link: '/guide/concepts' },
            ],
          },
          {
            text: 'Usage',
            items: [
              { text: 'Writing', link: '/guide/writing' },
              { text: 'Reading and Querying', link: '/guide/reading' },
              { text: 'Maintenance', link: '/guide/maintenance' },
              { text: 'LLM Integration', link: '/guide/llm-integration' },
              { text: 'Agent Memory (MCP)', link: '/guide/agent-memory' },
            ],
          },
          {
            text: 'Advanced',
            items: [
              { text: 'Operation Pipeline', link: '/guide/operations' },
              { text: 'Strategies', link: '/guide/strategies' },
              { text: 'Transactions and Consistency', link: '/guide/transactions' },
              { text: 'Deployment (GitHub Pages)', link: '/guide/deployment' },
            ],
          },
        ],

        '/design/': [
          {
            text: 'System Design',
            items: [
              { text: 'Design Philosophy', link: '/design/philosophy' },
              { text: 'Architecture Overview', link: '/design/architecture' },
              { text: 'Data Model', link: '/design/data-model' },
              { text: 'Maintenance Pipeline', link: '/design/maintenance' },
              { text: 'Transaction Model', link: '/design/transactions' },
              { text: 'ADR Records', link: '/design/adr' },
              { text: 'Evolution Roadmap', link: '/design/evolution' },
            ],
          },
        ],

        '/api/': [
          {
            text: 'API Reference',
            items: [
              { text: 'SemaFS Facade', link: '/api/semafs' },
              { text: 'Node and Path Model', link: '/api/node' },
              { text: 'Operations and Plans', link: '/api/operations' },
              { text: 'Storage and Unit of Work', link: '/api/repository' },
              { text: 'Strategies and Adapters', link: '/api/strategy' },
              { text: 'View Objects', link: '/api/views' },
            ],
          },
        ],
      },

      socialLinks: [{ icon: 'github', link: 'https://github.com/linzwcs/semafs' }],

      footer: {
        message: 'Released under the MIT License.',
        copyright: 'Copyright © 2026 SemaFS Contributors',
      },

      search: {
        provider: 'local',
      },

      editLink: {
        pattern: 'https://github.com/linzwcs/semafs/edit/main/docs/:path',
        text: 'Edit this page on GitHub',
      },
    },

    markdown: {
      lineNumbers: true,
    },
  })
)
