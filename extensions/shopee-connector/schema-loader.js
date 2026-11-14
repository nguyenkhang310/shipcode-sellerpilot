// Schema loader with version validation, priority precedence, and safe fallback.
let cachedSchema = null;

export async function fetchDefaultSchema() {
  // Check Node.js test environment first
  if (typeof process !== 'undefined' && process.versions?.node) {
    const fs = await import('node:fs');
    const {fileURLToPath} = await import('node:url');
    const file = fileURLToPath(new URL('shopee-schema.json', import.meta.url));
    return JSON.parse(fs.readFileSync(file, 'utf8'));
  }
  // Browser extension runtime
  if (typeof chrome !== 'undefined' && chrome.runtime?.getURL) {
    const url = chrome.runtime.getURL('shopee-schema.json');
    const response = await fetch(url);
    return response.json();
  }
  throw Error('Cannot resolve shopee-schema.json');
}

export function validateSchema(schema) {
  if (!schema || typeof schema !== 'object') return false;
  if (!schema.version || typeof schema.version !== 'string') return false;
  if (!schema.featureFlags || typeof schema.featureFlags !== 'object') return false;
  if (!schema.selectors || typeof schema.selectors !== 'object') return false;
  return true;
}

export async function loadSchema(forceReload = false) {
  if (cachedSchema && !forceReload) return cachedSchema;

  const defaultSchema = await fetchDefaultSchema();
  if (!validateSchema(defaultSchema)) {
    throw Error('shopee-schema.json mặc định không hợp lệ.');
  }

  let activeSchema = structuredClone(defaultSchema);

  // Check override from chrome.storage.local
  if (typeof chrome !== 'undefined' && chrome.storage?.local) {
    try {
      const {schema_override} = await chrome.storage.local.get('schema_override');
      if (schema_override) {
        if (validateSchema(schema_override) && schema_override.version === defaultSchema.version) {
          activeSchema = {
            ...defaultSchema,
            ...schema_override,
            featureFlags: {...defaultSchema.featureFlags, ...(schema_override.featureFlags || {})},
            selectors: {...defaultSchema.selectors, ...(schema_override.selectors || {})},
          };
        } else {
          console.warn('[WARN] schema_override không hợp lệ hoặc khác version, fallback về schema mặc định.');
        }
      }
    } catch {
      // Storage access error -> fallback to default
    }
  }

  cachedSchema = activeSchema;
  return activeSchema;
}

export async function isFeatureEnabled(flagName) {
  const schema = await loadSchema();
  return Boolean(schema.featureFlags?.[flagName]);
}

export async function getSelectorGroup(field) {
  const schema = await loadSchema();
  const group = schema.selectors?.[field];
  if (!group) return {primary: [], fallback: []};
  if (Array.isArray(group)) return {primary: group, fallback: []};
  return {
    primary: Array.isArray(group.primary) ? group.primary : [],
    fallback: Array.isArray(group.fallback) ? group.fallback : [],
  };
}
