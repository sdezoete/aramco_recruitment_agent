// node --test tests/js   (run from pytest by tests/test_frontend_js.py)
import { test } from "node:test";
import assert from "node:assert/strict";
import { cleanIds, ProfileNav, navAction, BlockCache, profileUrl } from "../../static/js/profile-nav.js";

test("cleanIds keeps order, drops duplicates and junk", () => {
  assert.deepEqual(cleanIds([3, "7", 3, 0, -1, 1.5, "x", null, 2147483648, 9]), [3, 7, 9]);
  assert.deepEqual(cleanIds(undefined), []);
});

test("ProfileNav steps within bounds", () => {
  const n = new ProfileNav([10, 20, 30], 0);
  assert.equal(n.current, 10);
  assert.equal(n.hasPrev, false);
  assert.equal(n.label, "1 of 3");
  assert.equal(n.prev(), 10, "prev at the start stays put");
  assert.equal(n.next(), 20);
  assert.equal(n.next(), 30);
  assert.equal(n.hasNext, false);
  assert.equal(n.next(), 30, "next at the end stays put");
  assert.equal(n.label, "3 of 3");
});

test("ProfileNav clamps the start index and handles a single candidate", () => {
  assert.equal(new ProfileNav([1, 2], 99).current, 2);
  assert.equal(new ProfileNav([1, 2], -4).current, 1);
  assert.equal(new ProfileNav([1, 2], "x").current, 1);
  const one = new ProfileNav([5]);
  assert.equal(one.label, "");
  assert.deepEqual(one.neighbours(), []);
  assert.throws(() => new ProfileNav([]));
  assert.throws(() => new ProfileNav(["junk"]));
});

test("ProfileNav goTo and neighbours", () => {
  const n = new ProfileNav([1, 2, 3, 4], 1);
  assert.deepEqual(n.neighbours(), [3, 1], "next first: it is the likely next click");
  assert.equal(n.goTo(4), true);
  assert.equal(n.current, 4);
  assert.deepEqual(n.neighbours(), [3]);
  assert.equal(n.goTo(99), false);
  assert.equal(n.current, 4);
});

test("navAction maps keys and leaves typing alone", () => {
  const ev = (key, tagName = "TR", extra = {}) => ({ key, target: { tagName }, ...extra });
  assert.equal(navAction(ev("ArrowDown")), "next");
  assert.equal(navAction(ev("j")), "next");
  assert.equal(navAction(ev("ArrowUp")), "prev");
  assert.equal(navAction(ev("k")), "prev");
  assert.equal(navAction(ev("Escape")), "close");
  assert.equal(navAction(ev("Escape", "TEXTAREA")), "close", "Esc closes even from the composer");
  assert.equal(navAction(ev("ArrowDown", "TEXTAREA")), null);
  assert.equal(navAction(ev("j", "INPUT")), null);
  assert.equal(navAction({ key: "j", target: { tagName: "DIV", isContentEditable: true } }), null);
  assert.equal(navAction(ev("ArrowDown", "TR", { ctrlKey: true })), null);
  assert.equal(navAction(ev("ArrowDown", "TR", { isComposing: true })), null);
  assert.equal(navAction(ev("Enter")), null);
  assert.equal(navAction(null), null);
});

test("BlockCache is per chat, LRU and clearable", () => {
  const c = new BlockCache(2);
  c.set("chatA", 1, { n: 1 });
  c.set("chatA", 2, { n: 2 });
  assert.equal(c.get("chatB", 1), undefined, "other chat does not see it");
  assert.deepEqual(c.get("chatA", 1), { n: 1 });   // 1 is now most recent
  c.set("chatA", 3, { n: 3 });                     // evicts 2
  assert.equal(c.get("chatA", 2), undefined);
  assert.deepEqual(c.get("chatA", 1), { n: 1 });
  assert.equal(c.size, 2);
  c.clear();
  assert.equal(c.size, 0);
});

test("profileUrl encodes its parts", () => {
  assert.equal(profileUrl("abc_123-xyz", 42), "/api/candidates/42/profile?chat_id=abc_123-xyz");
  assert.equal(profileUrl("a b&c", 7), "/api/candidates/7/profile?chat_id=a%20b%26c");
});
