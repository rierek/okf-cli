package yamlpatch

type editKind int

const (
	kindSetValue editKind = iota
	kindNewKey
	kindAppendItem
	kindRenameItem
	kindDeleteItem
	kindDeleteKey
	kindReplaceKey
	kindFlowToBlock
	kindSetBody
)

// Edit is one change to a stored file text; Apply runs a list of them in order. All edits address
// top-level keys of the frontmatter and the items of their list values.
type Edit struct {
	kind  editKind
	key   string // the key; the old key of a ReplaceKey
	key2  string // the new key of a ReplaceKey
	index int
	val   Value
	text  string // the new item of a RenameItem, the body of a SetBody
}

// SetValue sets the value of a key. An existing scalar keeps its quote or block style (a value that
// style cannot carry follows the quoting rule) and the trailing comment of its line; v must be a Str
// or a Plain then. A key the block lacks is added behind the last line of the block with any Value.
func SetValue(key string, v Value) Edit { return Edit{kind: kindSetValue, key: key, val: v} }

// NewKey adds a key that the block lacks behind the last line of the block. An existing key is
// refused.
func NewKey(key string, v Value) Edit { return Edit{kind: kindNewKey, key: key, val: v} }

// AppendItem adds an item (a Str, a Plain or a Map) to the list value of a key: behind the last item of
// a block list, ahead of the closing bracket of a flow list; one block mapping or one single-line flow
// mapping becomes the first item of a block list; a missing key is added as a new one-item list.
func AppendItem(key string, v Value) Edit { return Edit{kind: kindAppendItem, key: key, val: v} }

// RenameItem changes the scalar text of item index (0-based) of the list value of a key and keeps its
// quote style and trailing comment.
func RenameItem(key string, index int, s string) Edit {
	return Edit{kind: kindRenameItem, key: key, index: index, text: s}
}

// DeleteItem removes item index (0-based) of the list value of a key. Removing the only item leaves
// an empty flow list `[]` on the key line, which a following DeleteKey removes.
func DeleteItem(key string, index int) Edit {
	return Edit{kind: kindDeleteItem, key: key, index: index}
}

// DeleteKey removes a key with the lines of its value; the comment and blank lines around stay.
func DeleteKey(key string) Edit { return Edit{kind: kindDeleteKey, key: key} }

// ReplaceKey writes key (the old key or another one) with v in block style at the lines of oldKey.
func ReplaceKey(oldKey, key string, v Value) Edit {
	return Edit{kind: kindReplaceKey, key: oldKey, key2: key, val: v}
}

// FlowToBlock turns the non-empty flow list value of a key into a block list; the key line keeps its
// trailing comment at the column it had.
func FlowToBlock(key string) Edit { return Edit{kind: kindFlowToBlock, key: key} }

// SetBody replaces the text behind the closing delimiter; the head stays byte-identical.
func SetBody(body string) Edit { return Edit{kind: kindSetBody, text: body} }
