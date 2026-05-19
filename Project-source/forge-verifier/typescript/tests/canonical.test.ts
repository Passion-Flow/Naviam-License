import { test } from "node:test";
import assert from "node:assert/strict";

import { canonicalize } from "../src/canonical.js";

test("sorts object keys lexicographically", () => {
  assert.equal(canonicalize({ b: 1, a: 2, c: 3 }), '{"a":2,"b":1,"c":3}');
});

test("recursively canonicalises nested objects", () => {
  assert.equal(
    canonicalize({ z: { b: 1, a: 2 }, a: [3, 2, 1] }),
    '{"a":[3,2,1],"z":{"a":2,"b":1}}',
  );
});

test("no whitespace", () => {
  assert.equal(canonicalize({ a: { b: { c: 1 } } }), '{"a":{"b":{"c":1}}}');
});

test("strips undefined", () => {
  assert.equal(canonicalize({ a: 1, b: undefined }), '{"a":1}');
});
