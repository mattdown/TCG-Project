using System;
using System.Collections.Generic;
using Tcg.Protocol;
using Tcg.View;
using TMPro;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.UI;

namespace Tcg.Board
{
    /// <summary>
    /// The state graph the GNN reads (the server's graph request), drawn over a darkened board.
    /// Card nodes sit on their cards with the card's ability graph unfolded below them, the player
    /// nodes on the heroes and the global node halfway between them. Each node is a disc coloured by
    /// node type, with its vector (EmbeddingGlyph, greyscale) as a column inside; edges are coloured by edge type, and the
    /// legend hides an edge type when tapped. Nodes follow the cards every frame, so the graph
    /// keeps up with the board's animations. Top right, the legal actions and the value, with the
    /// legend below them: hovering a row (or tapping, to keep it) draws lines from the nodes its head reads.
    /// </summary>
    public class GraphOverlay : MonoBehaviour
    {
        static readonly string[] NodeOrder = { "card", "ability", "player", "global" };
        static readonly Dictionary<string, Color> NodeColours = new Dictionary<string, Color>
        {
            ["card"] = Palette.Hex("#3D7CF0"), ["ability"] = Palette.Hex("#B675FF"),
            ["player"] = Palette.Hex("#FFC93C"), ["global"] = Palette.Hex("#E9EEF8"),
        };

        struct EdgeStyle
        {
            public Color Colour;
            public float Width, Bend;
            public bool Arrow;
            public EdgeStyle(string hex, float alpha, float width, float bend, bool arrow)
            {
                Colour = Palette.Hex(hex).WithAlpha(alpha);
                Width = width;
                Bend = bend;
                Arrow = arrow;
            }
        }

        static readonly string[] EdgeOrder =
            { "next", "uses", "part_of", "matches", "bound_to", "belongs_to", "faces", "opposes", "in" };
        static readonly Dictionary<string, EdgeStyle> EdgeStyles = new Dictionary<string, EdgeStyle>
        {
            ["next"] = new EdgeStyle("#5BEA5B", 0.95f, 2f, 0f, true),
            ["uses"] = new EdgeStyle("#22BCC9", 0.95f, 1.5f, 0.45f, true),
            ["part_of"] = new EdgeStyle("#B675FF", 0.4f, 1f, 0f, false),
            ["matches"] = new EdgeStyle("#FF6FD8", 0.75f, 1.5f, 0.18f, true),
            ["bound_to"] = new EdgeStyle("#FFE14D", 0.95f, 2.5f, 0.25f, true),
            ["belongs_to"] = new EdgeStyle("#8FB3FF", 0.5f, 1.5f, 0f, false),
            ["faces"] = new EdgeStyle("#FF4D5E", 0.5f, 1.5f, 0.12f, false),
            ["opposes"] = new EdgeStyle("#FF8A3C", 0.9f, 2.5f, 0.2f, false),
            ["in"] = new EdgeStyle("#E9EEF8", 0.7f, 2f, 0f, false),
        };

        /// <summary>The policy head's inputs, in UiText.PolicySlots order: actor, target, context, option, global.</summary>
        static readonly Color[] SlotColours =
        {
            Palette.Hex("#FFE14D"), Palette.Hex("#FF4D5E"), Palette.Hex("#22BCC9"), Palette.Hex("#FF6FD8"),
            Palette.Hex("#E9EEF8"),
        };
        /// <summary>The value head's inputs, in UiText.ValueSlots order: global, you, opponent.</summary>
        static readonly Color[] ValueSlotColours = { SlotColours[4], Palette.Hex("#4ADE80"), Palette.Hex("#FF9F43") };
        const int MaxActionRows = 10;
        const float PanelWidth = 290f, PanelTop = 70f, PanelGap = 8f;

        class NodeView
        {
            public GraphNode Node;
            public RectTransform Rect;
            public CanvasGroup Group;
            public EmbeddingGlyph Glyph;
            public Image Frame, Back, Resolving;
            public Vector2 Position;
            public float Size;
            public int Layer, Index, Count;  // ability nodes: the place in their card's graph
        }

        /// <summary>The overlay opened, or wants a fresh graph: send the graph request.</summary>
        public event Action Requested;
        public bool IsOpen => _panel.activeSelf;

        BoardView _board;
        GameObject _panel;
        RectTransform _toggle;
        RectTransform _area, _nodeLayer;
        GraphEdges _edges;
        TMP_Text _caption;
        RectTransform _tooltip;
        TMP_Text _tooltipText;
        readonly Dictionary<string, (CanvasGroup group, TMP_Text label)> _edgeRows =
            new Dictionary<string, (CanvasGroup, TMP_Text)>();
        readonly HashSet<string> _hiddenEdges = new HashSet<string>();

        GraphData _graph;
        readonly List<NodeView> _nodes = new List<NodeView>();
        readonly Dictionary<int, List<NodeView>> _abilitiesOf = new Dictionary<int, List<NodeView>>();
        readonly Dictionary<int, Vector2Int> _treeSize = new Dictionary<int, Vector2Int>();  // card node → (depth, width)
        readonly List<GraphEdges.Edge> _edgeBuffer = new List<GraphEdges.Edge>();
        readonly Vector3[] _corners = new Vector3[4];
        int _hover = -1;
        bool _dirty;

        RectTransform _policy, _legend;
        readonly List<(int node, Color colour)> _focus = new List<(int, Color)>();
        RectTransform _focusRow;  // the action or value row whose inputs are drawn
        bool _pinned;

        public static GraphOverlay Create(RectTransform parent, BoardView board)
        {
            // Like the dev panel: raycasts pass through the full-screen root except on its button and open panel.
            var root = Ui.Stretch("Graph", parent, 0, 0, 0, 0);
            var view = root.gameObject.AddComponent<GraphOverlay>();
            view._board = board;

            var panel = Ui.Stretch("Panel", root, 0, 0, 0, 0);
            view._panel = panel.gameObject;
            Ui.Img(panel, null, new Color(8 / 255f, 14 / 255f, 32 / 255f, 0.86f)).raycastTarget = true;
            view._area = Ui.Stretch("Area", panel, 0, 0, 0, 0);
            var edges = Ui.Stretch("Edges", view._area, 0, 0, 0, 0).gameObject;
            edges.AddComponent<CanvasRenderer>();
            view._edges = edges.AddComponent<GraphEdges>();
            view._edges.raycastTarget = false;
            view._nodeLayer = Ui.Stretch("Nodes", view._area, 0, 0, 0, 0);
            view.BuildLegend(panel);
            view._policy = Ui.Node("Policy", panel);

            view._tooltip = Ui.Node("Tooltip", panel);
            view._tooltip.anchorMin = view._tooltip.anchorMax = new Vector2(0.5f, 0.5f);
            view._tooltip.pivot = new Vector2(0.5f, 0f);
            view._tooltipText = Ui.Pill(view._tooltip, "", Palette.Night, 12, display: false);
            view._tooltip.gameObject.SetActive(false);
            panel.gameObject.SetActive(false);

            var toggle = Ui.Node("Toggle", root);  // under the DEV button
            Ui.Anchor(toggle, Vector2.zero, Vector2.zero, new Vector2(182, 48), new Vector2(48, 22));
            Ui.Pill(toggle, UiText.GraphButton, Palette.Glass, 11, display: false);
            view._toggle = toggle;
            var button = toggle.gameObject.AddComponent<Button>();
            button.targetGraphic = toggle.GetComponent<Image>();
            toggle.GetComponent<Image>().raycastTarget = true;
            button.onClick.AddListener(view.Toggle);
            return view;
        }

        public void Toggle()
        {
            bool open = !IsOpen;
            _panel.SetActive(open);
            Ui.TintPill(_toggle, open ? Palette.HumanAccent : Palette.Glass);
            if (!open) return;
            transform.SetAsLastSibling();
            if (_graph == null) _caption.text = UiText.GraphLoading;
            Requested?.Invoke();
        }

        /// <summary>Draws a graph from the server, replacing the last one.</summary>
        public void Show(GraphData graph)
        {
            _graph = graph;
            foreach (var n in _nodes) Destroy(n.Rect.gameObject);
            _nodes.Clear();
            _abilitiesOf.Clear();
            _treeSize.Clear();
            _hover = -1;
            _focus.Clear();
            _focusRow = null;
            _pinned = false;
            _tooltip.gameObject.SetActive(false);

            int layer = graph.layers - 1;
            var scales = new Dictionary<string, float>();
            foreach (var type in NodeOrder) scales[type] = Scale(graph, type, layer);
            foreach (var node in graph.nodes)
            {
                var view = CreateNode(node);
                view.Glyph.Set(node.vectors[Mathf.Min(layer, node.vectors.Count - 1)], scales[node.type]);
                _nodes.Add(view);
                if (node.type == "ability" && node.card.HasValue)
                {
                    if (!_abilitiesOf.TryGetValue(node.card.Value, out var list))
                        _abilitiesOf[node.card.Value] = list = new List<NodeView>();
                    list.Add(view);
                }
            }
            foreach (var pair in _abilitiesOf) _treeSize[pair.Key] = LayOutTree(pair.Value);

            _caption.text = graph.embedding == "gnn" ? string.Format(UiText.GraphGnn, layer, graph.layers - 1)
                : UiText.GraphFeatures;
            var counts = new Dictionary<string, int>();
            foreach (var e in graph.edges) counts[e.type] = counts.TryGetValue(e.type, out var c) ? c + 1 : 1;
            foreach (var pair in _edgeRows)
                pair.Value.label.text = $"{Name(pair.Key)} <color=#B8C6E8>· {(counts.TryGetValue(pair.Key, out var n) ? n : 0)}</color>";
            BuildPolicy();
            _dirty = true;
            LateUpdate();
        }

        void LateUpdate()
        {
            if (_graph == null || !IsOpen) return;
            LayOut();
            if (_dirty) DrawEdges();
            _dirty = false;
        }

        // --- nodes

        NodeView CreateNode(GraphNode node)
        {
            var rt = Ui.Node($"{node.type} {node.id}", _nodeLayer);
            rt.anchorMin = rt.anchorMax = new Vector2(0.5f, 0.5f);
            var frame = Ui.Rounded(rt, NodeColours.TryGetValue(node.type, out var c) ? c : Color.white, 4);
            frame.raycastTarget = true;
            var group = rt.gameObject.AddComponent<CanvasGroup>();
            var back = Ui.Rounded(Ui.Stretch("Back", rt, 0, 0, 0, 0), Palette.Shadow, 3);
            // The vector is a column inside the disc; its rect is set by Place.
            var vector = Ui.Node("Vector", rt);
            vector.anchorMin = vector.anchorMax = new Vector2(0.5f, 0.5f);
            vector.gameObject.AddComponent<CanvasRenderer>();
            var glyph = vector.gameObject.AddComponent<EmbeddingGlyph>();
            glyph.raycastTarget = false;
            var resolving = node.resolving
                ? Ui.Outline(Ui.Stretch("Resolving", rt, -4, -4, -4, -4), Palette.GlowSelected, 6) : null;
            var hover = rt.gameObject.AddComponent<GraphNodeHover>();
            hover.Entered += () => SetHover(node.id);
            hover.Exited += () => { if (_hover == node.id) SetHover(-1); };
            return new NodeView { Node = node, Rect = rt, Group = group, Glyph = glyph, Frame = frame, Back = back,
                Resolving = resolving };
        }

        /// <summary>
        /// Places one card's ability nodes in layers along the next edges: each node one layer below
        /// the deepest step that leads to it, in the order a walk from the entries meets them.
        /// Returns (layers, widest layer).
        /// </summary>
        Vector2Int LayOutTree(List<NodeView> nodes)
        {
            var ids = new HashSet<int>();
            foreach (var n in nodes) ids.Add(n.Node.id);
            var children = new Dictionary<int, List<int>>();
            var parents = new Dictionary<int, int>();
            foreach (var id in ids)
            {
                children[id] = new List<int>();
                parents[id] = 0;
            }
            foreach (var e in _graph.edges)
                if (e.type == "next" && ids.Contains(e.src) && ids.Contains(e.dst))
                {
                    children[e.src].Add(e.dst);
                    parents[e.dst]++;
                }

            var depth = new Dictionary<int, int>();
            var order = new List<int>();
            var queue = new Queue<int>();
            var waiting = new Dictionary<int, int>(parents);
            foreach (var n in nodes)
                if (parents[n.Node.id] == 0)
                {
                    depth[n.Node.id] = 0;
                    queue.Enqueue(n.Node.id);
                }
            while (queue.Count > 0)  // longest path from an entry, in topological order
            {
                int id = queue.Dequeue();
                foreach (var child in children[id])
                {
                    depth[child] = Mathf.Max(depth.TryGetValue(child, out var d) ? d : 0, depth[id] + 1);
                    if (--waiting[child] == 0) queue.Enqueue(child);
                }
            }
            var seen = new HashSet<int>();
            void Walk(int id)
            {
                if (!seen.Add(id)) return;
                order.Add(id);
                foreach (var child in children[id]) Walk(child);
            }
            foreach (var n in nodes)
                if (parents[n.Node.id] == 0) Walk(n.Node.id);
            foreach (var n in nodes) Walk(n.Node.id);  // anything a cycle kept out of the walk

            var byId = new Dictionary<int, NodeView>();
            foreach (var n in nodes) byId[n.Node.id] = n;
            var layerCount = new Dictionary<int, int>();
            int layers = 0, width = 0;
            foreach (var id in order)
            {
                var n = byId[id];
                n.Layer = depth.TryGetValue(id, out var d) ? d : 0;
                n.Index = layerCount.TryGetValue(n.Layer, out var i) ? i : 0;
                layerCount[n.Layer] = n.Index + 1;
                layers = Mathf.Max(layers, n.Layer + 1);
                width = Mathf.Max(width, n.Index + 1);
            }
            foreach (var n in nodes) n.Count = layerCount[n.Layer];
            return new Vector2Int(layers, width);
        }

        void LayOut()
        {
            var area = _area.rect;
            var bounds = new Dictionary<int, Rect>();
            int unplaced = 0;
            foreach (var n in _nodes)
            {
                if (n.Node.type != "card") continue;
                var card = n.Node.uid.HasValue ? _board.CardByUid(n.Node.uid.Value) : null;
                bounds[n.Node.id] = card != null && card.gameObject.activeInHierarchy
                    ? BoundsOf(card.Rect)
                    // A card with no view (an action resolving from the discard pile): a slot mid-board.
                    : new Rect(-60 + unplaced++ * 140, -90, 120, 170);
            }

            foreach (var n in _nodes)
            {
                switch (n.Node.type)
                {
                    case "card":
                        LayOutCard(n, bounds, area);
                        break;
                    case "player":
                        var hero = n.Node.owner == 0 ? _board.HumanHero : _board.OpponentHero;
                        Place(n, BoundsOf(hero).center, 40);
                        break;
                    case "global":
                        // Halfway between the two player nodes, which both connect to it.
                        Place(n, (BoundsOf(_board.HumanHero).center + BoundsOf(_board.OpponentHero).center) / 2f, 36);
                        break;
                }
            }
        }

        /// <summary>The card node at the top of its card, and its ability graph unfolded below it within the card.</summary>
        void LayOutCard(NodeView n, Dictionary<int, Rect> bounds, Rect area)
        {
            var b = bounds[n.Node.id];
            // Fanned hand cards overlap: keep each graph within the gap to its neighbours.
            float width = b.width;
            foreach (var other in _nodes)
                if (other != n && other.Node.type == "card" && other.Node.zone == n.Node.zone &&
                    other.Node.owner == n.Node.owner && bounds.TryGetValue(other.Node.id, out var ob))
                {
                    float dx = Mathf.Abs(ob.center.x - b.center.x);
                    if (dx > 1f) width = Mathf.Min(width, dx);
                }

            float cardSize = Mathf.Clamp(b.width * 0.24f, 18f, 32f);
            float top = b.yMax - cardSize / 2f - 6f;
            float treeTop = top - cardSize / 2f - 4f;
            var size = _treeSize.TryGetValue(n.Node.id, out var s) ? s : Vector2Int.zero;
            float vStep = Mathf.Min(28f, (treeTop - b.yMin - 4f) / Mathf.Max(1, size.x));
            float hStep = Mathf.Min(26f, (width - 8f) / Mathf.Max(1, size.y));
            float nodeSize = Mathf.Clamp(Mathf.Min(vStep, hStep) - 5f, 9f, 20f);
            float lowest = size.x > 0 ? treeTop - (size.x - 0.5f) * vStep - nodeSize / 2f : top - cardSize / 2f;
            float shift = Mathf.Max(0f, area.yMin + 6f - lowest);  // a hand card cut off by the screen's edge

            Place(n, new Vector2(b.center.x, top + shift), cardSize);
            if (!_abilitiesOf.TryGetValue(n.Node.id, out var abilities)) return;
            foreach (var a in abilities)
                Place(a, new Vector2(b.center.x + (a.Index - (a.Count - 1) / 2f) * hStep,
                    treeTop - (a.Layer + 0.5f) * vStep + shift), nodeSize);
        }

        void Place(NodeView n, Vector2 position, float size)
        {
            if ((n.Position - position).sqrMagnitude < 0.01f && Mathf.Abs(n.Size - size) < 0.01f) return;
            n.Position = position;
            n.Size = size;
            n.Rect.anchoredPosition = position;
            n.Rect.sizeDelta = new Vector2(size, size);
            // Round nodes: a disc in the node type's colour, a navy ring inside, the vector as a column.
            float ring = Mathf.Max(2f, size * 0.16f);
            SetRadius(n.Frame, size / 2f);
            n.Back.rectTransform.offsetMin = new Vector2(ring, ring);
            n.Back.rectTransform.offsetMax = new Vector2(-ring, -ring);
            SetRadius(n.Back, size / 2f - ring);
            if (n.Resolving != null) SetRadius(n.Resolving, size / 2f + 4f);
            n.Glyph.rectTransform.sizeDelta = new Vector2(Mathf.Max(2f, size * 0.3f), size * 0.56f);
            _dirty = true;
        }

        static void SetRadius(Image img, float radius) =>
            img.pixelsPerUnitMultiplier = Ui.SliceRadius / Mathf.Max(radius, 0.5f);

        Rect BoundsOf(RectTransform rt)
        {
            rt.GetWorldCorners(_corners);
            Vector2 min = Vector2.positiveInfinity, max = Vector2.negativeInfinity;
            foreach (var corner in _corners)
            {
                Vector2 p = _area.InverseTransformPoint(corner);
                min = Vector2.Min(min, p);
                max = Vector2.Max(max, p);
            }
            return Rect.MinMaxRect(min.x, min.y, max.x, max.y);
        }

        /// <summary>A typical size of a node type's values in one layer (the 90th percentile of |v|).</summary>
        static float Scale(GraphData graph, string type, int layer)
        {
            var values = new List<float>();
            foreach (var n in graph.nodes)
                if (n.type == type && n.vectors.Count > 0)
                    foreach (var v in n.vectors[Mathf.Min(layer, n.vectors.Count - 1)]) values.Add(Mathf.Abs(v));
            if (values.Count == 0) return 1f;
            values.Sort();
            return Mathf.Max(values[(int)(0.9f * (values.Count - 1))], 1e-3f);
        }

        // --- edges

        void DrawEdges()
        {
            _edgeBuffer.Clear();
            foreach (var e in _graph.edges)
            {
                if (_hiddenEdges.Contains(e.type) || e.src >= _nodes.Count || e.dst >= _nodes.Count) continue;
                var style = EdgeStyles.TryGetValue(e.type, out var s) ? s : new EdgeStyle("#FFFFFF", 0.6f, 1f, 0f, false);
                var from = _nodes[e.src];
                var to = _nodes[e.dst];
                var colour = style.Colour;
                float width = style.Width;
                if (_focus.Count > 0)
                {
                    colour = colour.WithAlpha(colour.a * 0.12f);
                }
                else if (_hover >= 0)
                {
                    bool touches = e.src == _hover || e.dst == _hover;
                    colour = touches ? colour.WithAlpha(1f) : colour.WithAlpha(colour.a * 0.12f);
                    if (touches) width += 1f;
                }
                _edgeBuffer.Add(new GraphEdges.Edge
                {
                    From = from.Position, To = to.Position, Colour = colour, Width = width, Bend = style.Bend,
                    Inset = style.Arrow ? to.Size / 2f + 1f : 0f, Arrow = style.Arrow,
                });
            }
            if (_focusRow != null && _focus.Count > 0)
            {
                // The panel's left edge, level with the row: the lines are drawn under the panel.
                var to = new Vector2(BoundsOf(_policy).xMin, BoundsOf(_focusRow).center.y);
                foreach (var (node, colour) in _focus)
                    if (node < _nodes.Count)
                        _edgeBuffer.Add(new GraphEdges.Edge
                        {
                            From = _nodes[node].Position, To = to, Colour = colour, Width = 2.5f, Bend = 0.12f,
                            Arrow = true,
                        });
            }
            _edges.Set(_edgeBuffer);
        }

        void SetHover(int id)
        {
            _hover = id;
            _dirty = true;
            _tooltip.gameObject.SetActive(id >= 0);
            if (id < 0) return;
            var n = _nodes[id];
            _tooltipText.text = Describe(n.Node);
            _tooltip.anchoredPosition = n.Position + new Vector2(0, n.Size / 2f + 6f);
            _tooltip.SetAsLastSibling();
        }

        string Describe(GraphNode node)
        {
            switch (node.type)
            {
                case "card":
                    return $"{CardName(node.card_id)}\n<color=#B8C6E8>{node.type} · {(node.owner == 0 ? UiText.GraphYou : UiText.GraphOpponent)} · {node.zone}</color>";
                case "ability":
                    var card = node.card.HasValue && node.card.Value < _nodes.Count ? _nodes[node.card.Value].Node.card_id : null;
                    return $"{node.label}\n<color=#B8C6E8>{string.Format(UiText.GraphAbilityOf, CardName(card))}</color>";
                case "player":
                    return $"{(node.owner == 0 ? UiText.GraphYou : UiText.GraphOpponent)}\n<color=#B8C6E8>{node.type}</color>";
                default:
                    return $"{UiText.GraphGlobal}\n<color=#B8C6E8>{node.type}</color>";
            }
        }

        string CardName(string cardId) =>
            cardId != null && _board.Defs != null && _board.Defs.TryGetValue(cardId, out var def) ? def.name : cardId;

        static string Name(string type) => type.Replace('_', ' ');

        // --- legend

        void BuildLegend(RectTransform panel)
        {
            const float W = PanelWidth, Row = 17f;
            var legend = _legend = Ui.Node("Legend", panel);
            Ui.Rounded(legend, Palette.Shadow.WithAlpha(0.94f), 12).raycastTarget = true;
            float y = 10f;
            Ui.Display(Ui.Box("Title", legend, 12, y, W - 24, 22), UiText.GraphTitle, 18, TextAlignmentOptions.Left);
            y += 24f;
            _caption = Ui.Body(Ui.Box("Caption", legend, 12, y, W - 24, 16), "", 11, Palette.SubtleText);
            y += 20f;

            Ui.Text(Ui.Box("NodesHeader", legend, 12, y, W - 24, Row), UiText.GraphNodes, Ui.Theme.BodyBold, 12,
                Color.white, TextAlignmentOptions.Left);
            y += Row;
            for (int i = 0; i < NodeOrder.Length; i++)
            {
                float x = 12 + i % 4 * (W - 24) / 4f;
                var row = Ui.Box(NodeOrder[i], legend, x, y, (W - 24) / 4f, Row);
                Ui.Rounded(Ui.Box("Swatch", row, 0, 3, 11, 11), NodeColours[NodeOrder[i]], 5.5f);
                Ui.Text(Ui.Box("Label", row, 17, 0, 80, Row), NodeOrder[i], Ui.Theme.Body, 11, Color.white,
                    TextAlignmentOptions.Left);
            }
            y += Row + 4;

            Ui.Text(Ui.Box("EdgesHeader", legend, 12, y, W - 24, Row), UiText.GraphEdges, Ui.Theme.BodyBold, 12,
                Color.white, TextAlignmentOptions.Left);
            y += Row;
            float column = (W - 16) / 2f;
            int rows = (EdgeOrder.Length + 1) / 2;  // two columns, filled top to bottom
            for (int i = 0; i < EdgeOrder.Length; i++)
            {
                string type = EdgeOrder[i];
                var row = Ui.Box(type, legend, 8 + i / rows * column, y + i % rows * Row, column, Row);
                Ui.Img(row, null, Color.clear).raycastTarget = true;
                Ui.Img(Ui.Box("Swatch", row, 4, 6.5f, 18, 4), null, EdgeStyles[type].Colour.WithAlpha(1f));
                var label = Ui.Text(Ui.Box("Label", row, 28, 0, column - 30, Row), Name(type), Ui.Theme.Body, 11,
                    Color.white, TextAlignmentOptions.Left);
                var group = row.gameObject.AddComponent<CanvasGroup>();
                var button = row.gameObject.AddComponent<Button>();
                button.transition = Selectable.Transition.None;
                string t = type;
                button.onClick.AddListener(() => ToggleEdges(t));
                _edgeRows[type] = (group, label);
            }
            y += rows * Row + 4f;
            Ui.Body(Ui.Box("Hint", legend, 12, y, W - 24, 28), UiText.GraphHint, 10, Palette.SubtleText);
            y += 32f;
            Ui.Anchor(legend, new Vector2(1, 1), new Vector2(1, 1), new Vector2(-12, -PanelTop), new Vector2(W, y));
        }

        void ToggleEdges(string type)
        {
            if (!_hiddenEdges.Remove(type)) _hiddenEdges.Add(type);
            _edgeRows[type].group.alpha = _hiddenEdges.Contains(type) ? 0.35f : 1f;
            _dirty = true;
        }

        // --- policy and value

        /// <summary>
        /// The legal actions, likeliest first, and the value. Each row's slots are the nodes its
        /// head reads after message passing; an empty policy slot uses a learned "empty" vector.
        /// </summary>
        void BuildPolicy()
        {
            const float W = PanelWidth, Row = 20f;
            for (int i = _policy.childCount - 1; i >= 0; i--) Destroy(_policy.GetChild(i).gameObject);
            if (_policy.GetComponent<Image>() == null) Ui.Rounded(_policy, Palette.Shadow.WithAlpha(0.94f), 12).raycastTarget = true;

            float y = 10f;
            Ui.Display(Ui.Box("Title", _policy, 12, y, W - 24, 22), UiText.PolicyTitle, 18, TextAlignmentOptions.Left);
            y += 24f;
            Ui.Body(Ui.Box("Key", _policy, 12, y, W - 24, 30),
                string.Format(UiText.PolicyKey, SlotKey(UiText.PolicySlots, SlotColours)), 10, Palette.SubtleText);
            y += 30f;
            Ui.Body(Ui.Box("ValueKey", _policy, 12, y, W - 24, 16),
                string.Format(UiText.PolicyValueKey, SlotKey(UiText.ValueSlots, ValueSlotColours)), 10, Palette.SubtleText);
            y += 18f;

            var value = _graph.value;
            var valueSlots = new List<(int, Color)>();
            if (value?.nodes != null)
                for (int i = 0; i < value.nodes.Count && i < ValueSlotColours.Length; i++)
                    if (value.nodes[i] < _nodes.Count) valueSlots.Add((value.nodes[i], ValueSlotColours[i]));
            string estimate = value?.estimate.HasValue == true ? value.estimate.Value.ToString("+0.00;-0.00") : "–";
            PolicyRow(y, W, UiText.PolicyValue, estimate, null, valueSlots);
            y += Row + 6f;

            var actions = new List<GraphAction>(_graph.actions ?? new List<GraphAction>());
            actions.Sort((a, b) => (b.probability ?? 0f).CompareTo(a.probability ?? 0f));
            if (actions.Count == 0)
            {
                Ui.Body(Ui.Box("None", _policy, 12, y, W - 24, 30), UiText.PolicyNoActions, 11, Palette.SubtleText);
                y += 32f;
            }
            for (int i = 0; i < actions.Count && i < MaxActionRows; i++)
            {
                var a = actions[i];
                var slots = new List<(int, Color)>();
                var nodes = new[] { a.actor, a.target, a.context, a.option, a.global };
                for (int s = 0; s < nodes.Length; s++)
                    if (nodes[s].HasValue) slots.Add((nodes[s].Value, SlotColours[s]));
                string share = a.probability.HasValue ? $"{a.probability.Value:0%}" : "";
                PolicyRow(y, W, a.text, share, a.probability, slots);
                y += Row;
            }
            if (actions.Count > MaxActionRows)
            {
                Ui.Body(Ui.Box("More", _policy, 12, y + 2, W - 24, 16),
                    string.Format(UiText.PolicyMore, actions.Count - MaxActionRows), 11, Palette.SubtleText);
                y += Row;
            }
            // Top right, with the legend below it.
            Ui.Anchor(_policy, new Vector2(1, 1), new Vector2(1, 1), new Vector2(-12, -PanelTop), new Vector2(W, y + 8f));
            _legend.anchoredPosition = new Vector2(-12, -PanelTop - (y + 8f) - PanelGap);
        }

        static string SlotKey(string[] names, Color[] colours)
        {
            var key = new List<string>();
            for (int i = 0; i < names.Length; i++)
                key.Add($"<color=#{ColorUtility.ToHtmlStringRGB(colours[i])}>{names[i]}</color>");
            return string.Join(" · ", key);
        }

        void PolicyRow(float y, float width, string text, string right, float? share, List<(int, Color)> slots)
        {
            var row = Ui.Box("Row", _policy, 8, y, width - 16, 20);
            Ui.Rounded(row, Color.white.WithAlpha(0.06f), 5).raycastTarget = true;
            if (share.HasValue)
                Ui.Rounded(Ui.Box("Share", row, 0, 0, (width - 16) * Mathf.Clamp01(share.Value), 20),
                    Palette.HumanAccent.WithAlpha(0.55f), 5);
            var label = Ui.Text(Ui.Box("Text", row, 6, 0, width - 70, 20), text, Ui.Theme.Body, 11, Color.white,
                TextAlignmentOptions.Left);
            label.overflowMode = TextOverflowModes.Ellipsis;
            Ui.Text(Ui.Box("Right", row, width - 66, 0, 44, 20), right, Ui.Theme.BodyBold, 11, Color.white,
                TextAlignmentOptions.Right);
            var hover = row.gameObject.AddComponent<GraphNodeHover>();
            hover.Entered += () => { if (!_pinned) SetFocus(row, slots, false); };
            hover.Exited += () => { if (!_pinned && _focusRow == row) SetFocus(null, null, false); };
            var button = row.gameObject.AddComponent<Button>();
            button.transition = Selectable.Transition.None;
            button.onClick.AddListener(() =>
            {
                if (_pinned && _focusRow == row) SetFocus(null, null, false);
                else SetFocus(row, slots, true);
            });
        }

        /// <summary>Draws lines from the row's input nodes to the row and fades every other node.</summary>
        void SetFocus(RectTransform row, List<(int, Color)> slots, bool pin)
        {
            _focusRow = row;
            _pinned = pin && row != null;
            _focus.Clear();
            if (slots != null) _focus.AddRange(slots);
            var lit = new HashSet<int>();
            foreach (var (node, _) in _focus) lit.Add(node);
            foreach (var n in _nodes) n.Group.alpha = _focus.Count == 0 || lit.Contains(n.Node.id) ? 1f : 0.25f;
            _dirty = true;
        }
    }

    /// <summary>Tells the graph overlay which node the pointer is over.</summary>
    public class GraphNodeHover : MonoBehaviour, IPointerEnterHandler, IPointerExitHandler
    {
        public event Action Entered, Exited;
        public void OnPointerEnter(PointerEventData e) => Entered?.Invoke();
        public void OnPointerExit(PointerEventData e) => Exited?.Invoke();
    }
}
