"use client";

import React, { useState, useEffect } from "react";
import { CIRISClient } from "../../lib/cirisClient";

const client = new CIRISClient();

async function fetchScopes() {
  return { scopes: await client.memoryScopes() };
}

async function fetchEntry(scope: string, key: string) {
  const entries = await client.memoryEntries(scope);
  const match = entries.find((e: any) => e.key === key);
  return { value: match?.value };
}

async function storeEntry(scope: string, key: string, value: any) {
  await client.memoryStore(scope, key, value);
  return { result: 'ok' };
}

async function queryEntries(scope: string, prefix: string, limit: number) {
  const entries = await client.memoryEntries(scope);
  const filtered = entries.filter((e: any) => e.key.startsWith(prefix)).slice(0, limit);
  return { entries: filtered };
}

export default function MemoryPage() {
  const [scopes, setScopes] = useState<string[]>([]);
  const [selectedScope, setSelectedScope] = useState('');
  const [fetchKey, setFetchKey] = useState('');
  const [fetchResult, setFetchResult] = useState<any>(null);
  const [storeKey, setStoreKey] = useState('');
  const [storeValue, setStoreValue] = useState('{}');
  const [storeResult, setStoreResult] = useState<any>(null);
  const [queryPrefix, setQueryPrefix] = useState('');
  const [queryLimit, setQueryLimit] = useState(10);
  const [queryResult, setQueryResult] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchScopes().then(data => {
      setScopes(data.scopes || []);
      if (data.scopes && data.scopes.length > 0) setSelectedScope(data.scopes[0]);
    }).finally(() => setLoading(false));
  }, []);

  async function handleFetch(e: React.FormEvent) {
    e.preventDefault();
    setFetchResult(await fetchEntry(selectedScope, fetchKey));
  }

  async function handleStore(e: React.FormEvent) {
    e.preventDefault();
    try {
      const value = storeValue.trim() ? JSON.parse(storeValue) : {};
      setStoreResult(await storeEntry(selectedScope, storeKey, value));
    } catch {
      setStoreResult({ error: 'Invalid JSON value.' });
    }
  }

  async function handleQuery(e: React.FormEvent) {
    e.preventDefault();
    setQueryResult(await queryEntries(selectedScope, queryPrefix, queryLimit));
  }

  return (
    <div>
      <h1>Memory</h1>
      {loading ? <p>Loading...</p> : (
        <>
          <div style={{ marginBottom: 16 }}>
            <label>Scope: </label>
            <select value={selectedScope} onChange={e => setSelectedScope(e.target.value)}>
              {scopes.map(scope => <option key={scope} value={scope}>{scope}</option>)}
            </select>
          </div>
          <section style={{ marginBottom: 24 }}>
            <h2>Fetch Entry</h2>
            <form onSubmit={handleFetch} style={{ marginBottom: 8 }}>
              <input
                type="text"
                value={fetchKey}
                onChange={e => setFetchKey(e.target.value)}
                placeholder="Key"
                style={{ width: 200, marginRight: 8 }}
              />
              <button type="submit" disabled={!fetchKey}>Fetch</button>
            </form>
            {fetchResult && <pre style={{ background: '#f8f8f8', padding: 8, borderRadius: 4 }}>{JSON.stringify(fetchResult, null, 2)}</pre>}
          </section>
          <section style={{ marginBottom: 24 }}>
            <h2>Store Entry</h2>
            <form onSubmit={handleStore} style={{ marginBottom: 8 }}>
              <input
                type="text"
                value={storeKey}
                onChange={e => setStoreKey(e.target.value)}
                placeholder="Key"
                style={{ width: 200, marginRight: 8 }}
              />
              <textarea
                rows={2}
                style={{ width: 300, marginRight: 8 }}
                value={storeValue}
                onChange={e => setStoreValue(e.target.value)}
                placeholder="{ } (JSON value)"
              />
              <button type="submit" disabled={!storeKey}>Store</button>
            </form>
            {storeResult && <pre style={{ background: '#f8f8f8', padding: 8, borderRadius: 4 }}>{JSON.stringify(storeResult, null, 2)}</pre>}
          </section>
          <section>
            <h2>Query Entries</h2>
            <form onSubmit={handleQuery} style={{ marginBottom: 8 }}>
              <input
                type="text"
                value={queryPrefix}
                onChange={e => setQueryPrefix(e.target.value)}
                placeholder="Prefix (optional)"
                style={{ width: 200, marginRight: 8 }}
              />
              <input
                type="number"
                value={queryLimit}
                onChange={e => setQueryLimit(Number(e.target.value))}
                min={1}
                max={100}
                style={{ width: 80, marginRight: 8 }}
              />
              <button type="submit">Query</button>
            </form>
            {queryResult && <pre style={{ background: '#f8f8f8', padding: 8, borderRadius: 4 }}>{JSON.stringify(queryResult, null, 2)}</pre>}
          </section>
        </>
      )}
    </div>
  );
}
