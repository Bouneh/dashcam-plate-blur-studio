const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');

const root = path.resolve(__dirname, '..');
const source = fs.readFileSync(path.join(root, 'web', 'i18n.js'), 'utf8');
const html = fs.readFileSync(path.join(root, 'web', 'index.html'), 'utf8');

function load(initialLanguage) {
  const storage = new Map(initialLanguage ? [['plaque-studio-language', initialLanguage]] : []);
  const document = {
    documentElement: { lang: '' },
    title: '',
    querySelector: () => ({ content: '' }),
    querySelectorAll: () => [],
  };
  const context = {
    window: {},
    document,
    localStorage: {
      getItem: (key) => storage.get(key) ?? null,
      setItem: (key, value) => storage.set(key, value),
    },
  };
  vm.runInNewContext(source, context);
  return { i18n: context.window.PlaqueI18n, document, storage };
}

test('English is the default and French selection persists', () => {
  const { i18n, document, storage } = load();
  assert.equal(i18n.language, 'en');
  assert.equal(i18n.t('hero_line1'), 'Your videos.');
  i18n.setLanguage('fr');
  assert.equal(i18n.t('hero_line1'), 'Vos vidéos.');
  assert.equal(document.documentElement.lang, 'fr');
  assert.equal(storage.get('plaque-studio-language'), 'fr');
  assert.equal(load('fr').i18n.language, 'fr');
});

test('both dictionaries cover every static label', () => {
  const { i18n } = load();
  assert.deepEqual(Object.keys(i18n.messages.en).sort(), Object.keys(i18n.messages.fr).sort());
  const keys = [...html.matchAll(/data-i18n(?:-aria|-title)?="([^"]+)"/g)].map((match) => match[1]);
  for (const key of keys) {
    assert.ok(key in i18n.messages.en, `Missing English text: ${key}`);
    assert.ok(key in i18n.messages.fr, `Missing French text: ${key}`);
  }
});
