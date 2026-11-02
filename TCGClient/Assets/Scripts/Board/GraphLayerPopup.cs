using System;
using System.Collections.Generic;
using System.Linq;
using Tcg.Protocol;
using Tcg.View;
using TMPro;
using UnityEngine;

namespace Tcg.Board
{
    /// <summary>
    /// One GNN layer for one node, step by step (the server's graph_layer), over the node popup. On
    /// the left a lane per edge type, for one head (the chips switch head; ×4 on the lane's corner says
    /// how many): a row per neighbour with LeakyReLU(W_l·x_j + W_r·x_i), the score a· that,
    /// the attention and the weighted value; then the head's sum, and the heads joined into the
    /// edge type's message. On the right the steps after: the messages added, ReLU, the input added
    /// back, LayerNorm.
    /// </summary>
    public class GraphLayerPopup : MonoBehaviour
    {
        const float W = 1120f, H = 630f;
        // A strip's width is in proportion to its numbers: a head's 32 are a quarter of the message's 128.
        const float MessageW = 184f, StripW = MessageW / 4f;
        const float NameX = 24f, ValueX = 266f, QueryX = 344f, ScoreX = 450f, AttentionX = 502f, NumberW = 46f;
        const float WeightedX = 574f, LaneRight = WeightedX + MessageW + 32f, PipeX = 890f, PipeW = 206f;
        const float LanesTop = 112f, LanesBottom = H - 186f, MaxRowH = 20f, MinRowH = 14f, LaneGap = 8f;
        // The schematic: x_i at the centre, its neighbours x_j on the upper half of an ellipse around it.
        const float HubY = H - 98f, RingRX = 320f, RingRY = 62f, NeighbourSize = 22f, HubSize = 30f;

        RectTransform _content;
        readonly List<GraphEdges.Edge> _edges = new List<GraphEdges.Edge>();
        Func<int, string> _nameOf;
        Func<string, Color> _nodeColour, _edgeColour;
        GraphLayerDetail _layer;
        int _head, _perType;

        public static GraphLayerPopup Create(RectTransform parent, Func<int, string> nameOf,
            Func<string, Color> nodeColour, Func<string, Color> edgeColour)
        {
            var root = Ui.Stretch("LayerPopup", parent, 0, 0, 0, 0);
            var view = root.gameObject.AddComponent<GraphLayerPopup>();
            view._nameOf = nameOf;
            view._nodeColour = nodeColour;
            view._edgeColour = edgeColour;
            Ui.Scrim(root, "Scrim", 0.55f).onClick.AddListener(view.Hide);
            var card = Ui.Node("Card", root);
            Ui.Anchor(card, new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), Vector2.zero, new Vector2(W, H));
            Ui.Panel(card, 16, null, 1f).raycastTarget = true;
            view._content = Ui.Stretch("Content", card, 0, 0, 0, 0);
            var close = Ui.Node("Close", card);
            Ui.Anchor(close, new Vector2(1, 1), new Vector2(1, 1), new Vector2(-16, -14), new Vector2(96, 34));
            Ui.Button(close, UiText.NodeClose, Palette.Muted, 14, out _).onClick.AddListener(view.Hide);
            root.gameObject.SetActive(false);
            return view;
        }

        public void Hide() => gameObject.SetActive(false);

        public void Show(GraphLayerDetail layer)
        {
            _layer = layer;
            _head = Mathf.Clamp(_head, 0, Mathf.Max(0, layer.heads - 1));
            for (int i = _content.childCount - 1; i >= 0; i--) Destroy(_content.GetChild(i).gameObject);
            _edges.Clear();
            var lines = Ui.Stretch("Lines", _content, 0, 0, 0, 0).gameObject;
            lines.AddComponent<CanvasRenderer>();
            var graphic = lines.AddComponent<GraphEdges>();
            graphic.raycastTarget = false;
            gameObject.SetActive(true);
            transform.SetAsLastSibling();

            var title = Ui.Display(Ui.Box("Title", _content, 24, 14, W - 160, 28),
                string.Format(UiText.LayerTitle, layer.layer, layer.layers, _nameOf(layer.node)), 22,
                TextAlignmentOptions.Left);
            title.overflowMode = TextOverflowModes.Ellipsis;
            Text("Subtitle", 24, 46, PipeX - 40f, 34, UiText.LayerSubtitle, 12, Palette.SubtleText)
                .textWrappingMode = TextWrappingModes.Normal;
            HeadChips(layer);

            float[] columns = { ValueX, QueryX, ScoreX, AttentionX, WeightedX };
            for (int c = 0; c < columns.Length; c++)
                Text("Column", columns[c], 90, c == columns.Length - 1 ? MessageW : QueryX - ValueX, 16,
                    UiText.LayerColumns[c], 11, Color.white, true);

            BuildLanes(layer);
            BuildSchematic(layer);
            BuildSteps(layer);
            var formula = Text("Formula", NameX, H - 62, PipeX - NameX - 24, 50,
                string.Format(UiText.LayerFormula, layer.negative_slope, layer.heads, layer.head_dim, layer.hidden), 10,
                Palette.SubtleText);
            formula.textWrappingMode = TextWrappingModes.Normal;
            graphic.Set(_edges);
        }

        /// <summary>A chip per head: tapping one redraws the lanes for it.</summary>
        void HeadChips(GraphLayerDetail layer)
        {
            // Below the close button, which covers this corner.
            Text("Head", PipeX, 66, 40f, 22, UiText.LayerHead, 11, Palette.SubtleText);
            for (int h = 0; h < layer.heads; h++)
            {
                int head = h;
                var chip = Ui.Box("Chip", _content, PipeX + 40f + h * 34f, 66f, 30f, 22f);
                Ui.Button(chip, (h + 1).ToString(), h == _head ? Palette.Lantern : Palette.Muted, 12, out _, h == _head, 6)
                    .onClick.AddListener(() => { _head = head; Show(_layer); });
            }
        }

        // --- a lane per edge type

        void BuildLanes(GraphLayerDetail layer)
        {
            var types = layer.edge_types ?? new List<LayerEdgeType>();
            float room = LanesBottom - LanesTop - LaneGap * types.Count;
            // Every neighbour if they fit (rows shrinking to MinRowH first), else the most per type that do.
            int perType = types.Count > 0 ? types.Max(t => t.neighbours.Count) : 0;
            while (perType > 1 && room / Rows(types, perType) < MinRowH) perType--;
            _perType = perType;
            float rowH = types.Count > 0 ? Mathf.Min(MaxRowH, room / Rows(types, perType)) : MaxRowH;
            int h = _head;

            float y = LanesTop;
            foreach (var t in types)
            {
                var colour = _edgeColour(t.shown_as);
                int shown = Mathf.Min(perType, t.neighbours.Count);
                int rows = 3 + shown + (t.neighbours.Count > shown ? 1 : 0);
                const float right = LaneRight;
                Ui.Rounded(Ui.Box("Lane", _content, NameX - 8f, y - 2f, right - NameX + 8f, rowH * rows + 4f),
                    Color.white.WithAlpha(0.03f), 6);
                // One head is shown; this says how many there are.
                Text("Heads", right - 44f, y, 38f, rowH, string.Format(UiText.LayerHeads, layer.heads), 11, Color.white,
                    true, TextAlignmentOptions.Right);
                Ui.Img(Ui.Box("Swatch", _content, NameX, y + rowH / 2f - 2f, 16, 4), null, colour);
                string label = t.shown_as == t.type ? Name(t.type)
                    : string.Format(UiText.NodeReverse, Name(t.type), Name(t.shown_as));
                Text("Type", NameX + 22f, y, WeightedX - NameX - 22f, rowH, label, 11, Color.white, true);
                y += rowH;

                // One scale per column, so the rows compare: a weighted value is its value shrunk by the attention.
                // A head's numbers averaged into cells like the message's, a quarter as many for a quarter the numbers.
                int cells = Mathf.Max(1, t.message.Count * layer.head_dim / layer.hidden);
                List<float> Cells(List<float> v) => Average(v, cells);
                float valueScale = Scale(t.neighbours.Take(shown).Select(n => Cells(n.value[h])));
                float queryScale = Scale(new[] { Cells(t.query[h]) });
                for (int k = 0; k < shown; k++)
                {
                    var n = t.neighbours[k];
                    float mid = y + rowH / 2f;
                    Text("Neighbour", NameX + 10f, y, ValueX - NameX - 24f, rowH, "← " + _nameOf(n.node), 10,
                        Palette.LanternText);
                    Strip(Cells(n.value[h]), ValueX, y, rowH, colour, StripW, valueScale, layer.head_dim);
                    Strip(Cells(t.query[h]), QueryX, y, rowH, _nodeColour(layer.type), StripW, queryScale, layer.head_dim);
                    Arrow(QueryX + StripW + 16f, ScoreX - 3f, mid);
                    Text("Score", ScoreX, y, NumberW - 6f, rowH, n.scores[h].ToString("0.0"), 10, Palette.LanternText,
                        false, TextAlignmentOptions.Right);
                    float a = n.attention[h];
                    Ui.Rounded(Ui.Box("Attention", _content, AttentionX, y + 1f, NumberW, rowH - 2f),
                        Palette.Lantern.WithAlpha(0.06f + 0.6f * a), 3);
                    Text("Value", AttentionX, y, NumberW, rowH, a.ToString("0.00"), 9, Color.white, false,
                        TextAlignmentOptions.Center);
                    Arrow(AttentionX + NumberW + 2f, WeightedX - 3f, mid);
                    Strip(Cells(n.weighted[h]), WeightedX, y, rowH, colour, StripW, valueScale, layer.head_dim);
                    y += rowH;
                }
                if (shown < t.neighbours.Count)
                {
                    Text("More", NameX + 10f, y, ValueX - NameX - 24f, rowH,
                        string.Format(UiText.NodeMore, t.neighbours.Count - shown), 10, Palette.SubtleText);
                    y += rowH;
                }

                Text("HeadSum", NameX + 10f, y, ValueX - NameX - 24f, rowH, string.Format(UiText.LayerHeadSum, h + 1), 10,
                    Color.white, true);
                Text("Sigma", WeightedX - 16f, y, 14f, rowH, "Σ", 11, Color.white, true, TextAlignmentOptions.Center);
                Strip(Cells(t.heads[h]), WeightedX, y, rowH, colour, StripW, valueScale, layer.head_dim);
                y += rowH;

                Text("Message", NameX + 10f, y, ScoreX - NameX - 10f, rowH,
                    string.Format(UiText.LayerJoined, layer.heads), 10, Color.white, true);
                Text("Length", ScoreX, y, WeightedX - ScoreX - 20f, rowH,
                    string.Format(UiText.LayerLength, t.message_size.ToString("0.0")), 10, Palette.SubtleText, false,
                    TextAlignmentOptions.Right);
                Strip(t.message, WeightedX, y, rowH, colour, MessageW, 0f, layer.hidden);
                // Every edge type's message goes into the sum on the right.
                _edges.Add(new GraphEdges.Edge
                {
                    From = P(right + 2f, y + rowH / 2f), To = P(PipeX - 4f, StepY(1) + 29f),
                    Colour = colour.WithAlpha(0.7f), Width = 1.5f, Bend = -0.08f, Arrow = true,
                });
                y += rowH + LaneGap;
            }
        }

        /// <summary>v averaged down to n numbers, in runs of equal length (as the server averages the message).</summary>
        static List<float> Average(List<float> v, int n)
        {
            int run = Mathf.Max(1, v.Count / n);
            return Enumerable.Range(0, Mathf.Min(n, v.Count)).Select(i => v.Skip(i * run).Take(run).Average()).ToList();
        }

        static float Scale(IEnumerable<List<float>> vectors) =>
            vectors.SelectMany(v => v).Select(Mathf.Abs).DefaultIfEmpty(1f).Max();

        // --- the schematic: which nodes x_j send to x_i

        /// <summary>
        /// x_i in its node type's colour with its neighbours x_j around it, drawn like the overlay's
        /// nodes; each line in its edge type's colour, as thick as the attention in the head shown.
        /// </summary>
        void BuildSchematic(GraphLayerDetail layer)
        {
            var senders = (layer.edge_types ?? new List<LayerEdgeType>())
                .SelectMany(t => t.neighbours.Take(_perType).Select(n => (type: t, node: n))).ToList();
            var hub = new Vector2((NameX + LaneRight) / 2f, HubY);
            Text("SchematicNote", NameX, LanesBottom + 4f, 220f, 30f, string.Format(UiText.LayerSchematic, _head + 1), 10,
                Palette.SubtleText).textWrappingMode = TextWrappingModes.Normal;
            for (int k = 0; k < senders.Count; k++)
            {
                var (t, n) = senders[k];
                float angle = Mathf.PI * (1f - (k + 0.5f) / senders.Count);  // left to right, in lane order
                var at = hub + new Vector2(RingRX * Mathf.Cos(angle), -RingRY * Mathf.Sin(angle));
                float a = n.attention[_head];
                var towards = (hub - at).normalized;
                _edges.Add(new GraphEdges.Edge
                {
                    From = P(at.x, at.y) + new Vector2(towards.x, -towards.y) * (NeighbourSize / 2f),
                    To = P(hub.x, hub.y) - new Vector2(towards.x, -towards.y) * (HubSize / 2f + 2f),
                    Colour = _edgeColour(t.shown_as).WithAlpha(0.35f + 0.65f * a), Width = 1f + 3f * a, Arrow = true,
                });
                Disc(at, NeighbourSize, _nodeColour(t.source), n.embedding);
                Text("Xj", at.x - 20f, at.y - NeighbourSize / 2f - 14f, 40f, 13f, UiText.LayerNeighbourNode, 10,
                    Color.white, false, TextAlignmentOptions.Center);
            }
            Disc(hub, HubSize, _nodeColour(layer.type), layer.input.vector);
            // Under the node: every line comes in from above.
            Text("Xi", hub.x - 20f, hub.y + HubSize / 2f + 1f, 40f, 16f, UiText.LayerNode, 12, Color.white, true,
                TextAlignmentOptions.Center);
        }

        /// <summary>A node as the overlay draws one: a disc in its type's colour, a dark ring inside, its vector as a column.</summary>
        void Disc(Vector2 centre, float size, Color colour, List<float> vector)
        {
            var rt = Ui.Box("Node", _content, centre.x - size / 2f, centre.y - size / 2f, size, size);
            Ui.Rounded(rt, colour, size / 2f);
            float ring = Mathf.Max(2f, size * 0.16f);
            Ui.Rounded(Ui.Stretch("Back", rt, ring, ring, ring, ring), Palette.Shadow, size / 2f - ring);
            if (vector == null || vector.Count == 0) return;
            var column = Ui.Node("Vector", rt);
            Ui.Anchor(column, new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), Vector2.zero,
                new Vector2(Mathf.Max(2f, size * 0.3f), size * 0.56f));
            column.gameObject.AddComponent<CanvasRenderer>();
            var glyph = column.gameObject.AddComponent<EmbeddingGlyph>();
            glyph.raycastTarget = false;
            glyph.Set(vector, vector.Max(v => Mathf.Abs(v)));
        }

        static float Rows(List<LayerEdgeType> types, int perType) =>
            types.Sum(t => 3 + Mathf.Min(t.neighbours.Count, perType) + (t.neighbours.Count > perType ? 1 : 0));

        // --- the steps after the messages

        static float StepY(int i) => LanesTop + i * 74f;

        void BuildSteps(GraphLayerDetail layer)
        {
            var steps = new[] { layer.input, layer.sum, layer.relu, layer.residual, layer.output };
            for (int i = 0; i < steps.Length; i++)
            {
                float y = StepY(i);
                string label = string.Format(UiText.LayerSteps[i], layer.layer);
                Text("Step", PipeX, y, PipeW - 70f, 16, label, 11, Color.white, true);
                Text("Length", PipeX + PipeW - 70f, y, 70f, 16,
                    string.Format(UiText.LayerLength, steps[i].size.ToString("0.0")), 10, Palette.SubtleText, false,
                    TextAlignmentOptions.Right);
                var colour = i == 0 || i == steps.Length - 1 ? _nodeColour(layer.type) : Palette.Lantern;
                Strip(steps[i].vector, PipeX, y + 20f, 18f, colour, PipeW);
                if (i > 1)
                    _edges.Add(new GraphEdges.Edge
                    {
                        From = P(PipeX + PipeW / 2f, StepY(i - 1) + 40f), To = P(PipeX + PipeW / 2f, y - 2f),
                        Colour = Color.white.WithAlpha(0.55f), Width = 1.5f, Arrow = true,
                    });
            }
            // The residual: the input skips the messages and is added back before LayerNorm.
            _edges.Add(new GraphEdges.Edge
            {
                From = P(PipeX + PipeW + 3f, StepY(0) + 29f), To = P(PipeX + PipeW + 3f, StepY(3) + 29f),
                Colour = _nodeColour(layer.type).WithAlpha(0.8f), Width = 1.5f, Bend = 0.05f, Arrow = true,
            });
        }

        // --- drawing helpers

        /// <summary>A vector as a row of cells in a frame of <paramref name="colour"/>, at (x, y) in a row of height h;
        /// shaded against <paramref name="scale"/>, or the vector's own biggest number; <paramref name="size"/>, its
        /// count of numbers, goes in small on the top-right corner.</summary>
        void Strip(List<float> values, float x, float y, float h, Color colour, float w = StripW, float scale = 0f,
            int size = 0)
        {
            var frame = Ui.Box("Strip", _content, x, y + 2f, w, Mathf.Max(6f, h - 4f));
            if (size > 0)
                Text("Size", x + w + 1f, y - 1f, 22f, 10f, size.ToString(), 7, Palette.SubtleText);
            Ui.Rounded(frame, colour, 3);
            Ui.Rounded(Ui.Stretch("Back", frame, 1.5f, 1.5f, 1.5f, 1.5f), Palette.Shadow, 2);
            if (values == null || values.Count == 0) return;
            var cells = Ui.Stretch("Cells", frame, 1.5f, 1.5f, 1.5f, 1.5f).gameObject;
            cells.AddComponent<CanvasRenderer>();
            var glyph = cells.AddComponent<EmbeddingGlyph>();
            glyph.raycastTarget = false;
            glyph.Horizontal = true;
            glyph.Set(values, scale > 0f ? scale : values.Max(v => Mathf.Abs(v)));
        }

        void Arrow(float x0, float x1, float y) =>
            _edges.Add(new GraphEdges.Edge
            {
                From = P(x0, y), To = P(x1, y), Colour = Color.white.WithAlpha(0.4f), Width = 1.2f, Arrow = true,
            });

        static string Name(string type) => type.Replace('_', ' ');

        /// <summary>A point given from the panel's top-left, in the line graphic's centred space.</summary>
        static Vector2 P(float x, float y) => new Vector2(x - W / 2f, H / 2f - y);

        TextMeshProUGUI Text(string name, float x, float y, float w, float h, string text, float size, Color colour,
            bool bold = false, TextAlignmentOptions align = TextAlignmentOptions.Left)
        {
            var t = Ui.Text(Ui.Box(name, _content, x, y, w, h), text, bold ? Ui.Theme.BodyBold : Ui.Theme.Body, size,
                colour, align);
            t.overflowMode = TextOverflowModes.Ellipsis;
            return t;
        }
    }
}
