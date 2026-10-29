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
    /// nodes on the heroes and the global node by the turn counter. Each node shows its vector
    /// (EmbeddingGlyph) in a frame coloured by node type; edges are coloured by edge type, and the
    /// legend hides an edge type when tapped. Nodes follow the cards every frame, so the graph
    /// keeps up with the board's animations.
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

        class NodeView
        {
            public GraphNode Node;
            public RectTransform Rect;
            public EmbeddingGlyph Glyph;
            public Vector2 Position;
            public float Size;
            public int Layer, Index, Count;  // ability nodes: the place in their card's graph
        }

        /// <summary>The overlay opened, or wants a fresh graph: send the graph request.</summary>
        public event Action Requested;
        public bool IsOpen => _panel.activeSelf;

        BoardView _board;
        GameObject _panel;
        Image _toggleFace;
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

            view._tooltip = Ui.Node("Tooltip", panel);
            view._tooltip.anchorMin = view._tooltip.anchorMax = new Vector2(0.5f, 0.5f);
            view._tooltip.pivot = new Vector2(0.5f, 0f);
            view._tooltipText = Ui.Pill(view._tooltip, "", Palette.UiNavy, 12, display: false);
            view._tooltip.gameObject.SetActive(false);
            panel.gameObject.SetActive(false);

            var toggle = Ui.Box("Toggle", root, 80, 690, 48, 22, bottom: true);
            Ui.Pill(toggle, UiText.GraphButton, Palette.CardNavy, 11, display: false);
            view._toggleFace = toggle.Find("Face").GetComponent<Image>();
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
            _toggleFace.color = open ? Palette.HumanAccent : Palette.CardNavy;
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
            Ui.Rounded(Ui.Stretch("Back", rt, 2, 2, 2, 2), Palette.Outline, 3);
            var vector = Ui.Stretch("Vector", rt, 3, 3, 3, 3).gameObject;
            vector.AddComponent<CanvasRenderer>();
            var glyph = vector.AddComponent<EmbeddingGlyph>();
            glyph.raycastTarget = false;
            if (node.resolving)
                Ui.Outline(Ui.Stretch("Resolving", rt, -4, -4, -4, -4), Palette.GlowSelected, 6);
            var hover = rt.gameObject.AddComponent<GraphNodeHover>();
            hover.Entered += () => SetHover(node.id);
            hover.Exited += () => { if (_hover == node.id) SetHover(-1); };
            return new NodeView { Node = node, Rect = rt, Glyph = glyph };
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
                        Place(n, BoundsOf(_board.TurnText.rectTransform).center + new Vector2(0, 48), 36);
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
            _dirty = true;
        }

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
                if (_hover >= 0)
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
            const float W = 220f, Row = 17f;
            var legend = Ui.Node("Legend", panel);
            Ui.Rounded(legend, Palette.Outline.WithAlpha(0.94f), 12).raycastTarget = true;
            float y = 10f;
            Ui.Display(Ui.Box("Title", legend, 12, y, W - 24, 22), UiText.GraphTitle, 18, TextAlignmentOptions.Left);
            y += 24f;
            _caption = Ui.Body(Ui.Box("Caption", legend, 12, y, W - 24, 28), "", 11, Palette.SubtleText);
            y += 30f;

            Ui.Text(Ui.Box("NodesHeader", legend, 12, y, W - 24, Row), UiText.GraphNodes, Ui.Theme.NunitoBlack, 12,
                Color.white, TextAlignmentOptions.Left);
            y += Row;
            for (int i = 0; i < NodeOrder.Length; i++)
            {
                float x = 12 + i % 2 * (W - 24) / 2f;
                var row = Ui.Box(NodeOrder[i], legend, x, y + i / 2 * Row, (W - 24) / 2f, Row);
                Ui.Rounded(Ui.Box("Swatch", row, 0, 3, 11, 11), NodeColours[NodeOrder[i]], 3);
                Ui.Text(Ui.Box("Label", row, 17, 0, 80, Row), NodeOrder[i], Ui.Theme.Nunito, 11, Color.white,
                    TextAlignmentOptions.Left);
            }
            y += Row * 2 + 4;

            Ui.Text(Ui.Box("EdgesHeader", legend, 12, y, W - 24, Row), UiText.GraphEdges, Ui.Theme.NunitoBlack, 12,
                Color.white, TextAlignmentOptions.Left);
            y += Row;
            foreach (var type in EdgeOrder)
            {
                var row = Ui.Box(type, legend, 8, y, W - 16, Row);
                Ui.Img(row, null, Color.clear).raycastTarget = true;
                Ui.Img(Ui.Box("Swatch", row, 4, 6.5f, 22, 4), null, EdgeStyles[type].Colour.WithAlpha(1f));
                var label = Ui.Text(Ui.Box("Label", row, 34, 0, W - 50, Row), Name(type), Ui.Theme.Nunito, 11,
                    Color.white, TextAlignmentOptions.Left);
                var group = row.gameObject.AddComponent<CanvasGroup>();
                var button = row.gameObject.AddComponent<Button>();
                button.transition = Selectable.Transition.None;
                string t = type;
                button.onClick.AddListener(() => ToggleEdges(t));
                _edgeRows[type] = (group, label);
                y += Row;
            }
            y += 4f;
            Ui.Body(Ui.Box("Hint", legend, 12, y, W - 24, 44), UiText.GraphHint, 10, Palette.SubtleText);
            y += 48f;
            Ui.Anchor(legend, new Vector2(1, 1), new Vector2(1, 1), new Vector2(-12, -70), new Vector2(W, y));
        }

        void ToggleEdges(string type)
        {
            if (!_hiddenEdges.Remove(type)) _hiddenEdges.Add(type);
            _edgeRows[type].group.alpha = _hiddenEdges.Contains(type) ? 0.35f : 1f;
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
