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
    /// the left a lane per edge type: this node's query, then a row per neighbour (its embedding, its
    /// value, its score and attention per head) and the message they add up to. On the right the
    /// steps after: the messages added, ReLU, the input added back, LayerNorm.
    /// </summary>
    public class GraphLayerPopup : MonoBehaviour
    {
        const float W = 1120f, H = 630f;
        const float NameX = 24f, NameW = 214f, EmbX = 246f, ValueX = 394f, StripW = 120f;
        const float ScoresX = 540f, AttentionX = 704f, HeadsW = 152f, PipeX = 890f, PipeW = 206f;
        const float LanesTop = 112f, LanesBottom = H - 72f, MaxRowH = 20f, MinRowH = 14f, LaneGap = 8f;

        RectTransform _content;
        readonly List<GraphEdges.Edge> _edges = new List<GraphEdges.Edge>();
        Func<int, string> _nameOf;
        Func<string, Color> _nodeColour, _edgeColour;

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
            Text("Subtitle", 24, 46, W - 160, 18, string.Format(UiText.LayerSubtitle, layer.heads, layer.head_dim), 12,
                Palette.SubtleText);
            float[] columns = { EmbX, ValueX, ScoresX, AttentionX };
            for (int c = 0; c < columns.Length; c++)
                Text("Column", columns[c], 84, c < 2 ? StripW : HeadsW, 16, UiText.LayerColumns[c], 11, Color.white, true);

            BuildLanes(layer);
            BuildSteps(layer);
            var formula = Text("Formula", NameX, H - 62, PipeX - NameX - 24, 50,
                string.Format(UiText.LayerFormula, layer.negative_slope, layer.heads, layer.head_dim), 10,
                Palette.SubtleText);
            formula.textWrappingMode = TextWrappingModes.Normal;
            graphic.Set(_edges);
        }

        // --- a lane per edge type

        void BuildLanes(GraphLayerDetail layer)
        {
            var types = layer.edge_types ?? new List<LayerEdgeType>();
            float room = LanesBottom - LanesTop - LaneGap * types.Count;
            // Every neighbour if they fit (rows shrinking to MinRowH first), else the most per type that do.
            int perType = types.Count > 0 ? types.Max(t => t.neighbours.Count) : 0;
            while (perType > 1 && room / Rows(types, perType) < MinRowH) perType--;
            float rowH = types.Count > 0 ? Mathf.Min(MaxRowH, room / Rows(types, perType)) : MaxRowH;
            float headW = HeadsW / Mathf.Max(1, layer.heads);

            float y = LanesTop;
            foreach (var t in types)
            {
                var colour = _edgeColour(t.shown_as);
                Ui.Rounded(Ui.Box("Lane", _content, NameX - 8f, y - 2f, AttentionX + HeadsW - NameX + 16f,
                    rowH * (2 + Mathf.Min(perType, t.neighbours.Count) + (t.neighbours.Count > perType ? 1 : 0)) + 4f),
                    Color.white.WithAlpha(0.03f), 6);
                Ui.Img(Ui.Box("Swatch", _content, NameX, y + rowH / 2f - 2f, 16, 4), null, colour);
                string label = t.shown_as == t.type ? Name(t.type)
                    : string.Format(UiText.NodeReverse, Name(t.type), Name(t.shown_as));
                Text("Type", NameX + 22f, y, NameW - 22f, rowH, label, 11, Color.white, true);
                Text("Query", EmbX, y, StripW + 20f, rowH, UiText.LayerQuery, 10, Palette.SubtleText, false,
                    TextAlignmentOptions.Right);
                Strip(t.query, ValueX, y, rowH, _nodeColour(layer.type));
                y += rowH;

                int shown = Mathf.Min(perType, t.neighbours.Count);
                for (int k = 0; k < shown; k++)
                {
                    var n = t.neighbours[k];
                    Text("Neighbour", NameX + 10f, y, NameW - 10f, rowH, "← " + _nameOf(n.node), 10, Palette.LanternText);
                    Strip(n.embedding, EmbX, y, rowH, _nodeColour(t.source));
                    Arrow(EmbX + StripW + 3f, ValueX - 3f, y + rowH / 2f);
                    Strip(n.value, ValueX, y, rowH, colour);
                    for (int h = 0; h < n.scores.Count; h++)
                        Text("Score", ScoresX + h * headW, y, headW - 4f, rowH, n.scores[h].ToString("0.0"), 10,
                            Palette.LanternText, false, TextAlignmentOptions.Right);
                    for (int h = 0; h < n.attention.Count; h++)
                    {
                        float a = n.attention[h];
                        Ui.Rounded(Ui.Box("Attention", _content, AttentionX + h * headW, y + 1f, headW - 3f, rowH - 2f),
                            Palette.Lantern.WithAlpha(0.06f + 0.6f * a), 3);
                        Text("Value", AttentionX + h * headW, y, headW - 3f, rowH, a.ToString("0.00"), 9, Color.white,
                            false, TextAlignmentOptions.Center);
                    }
                    y += rowH;
                }
                if (shown < t.neighbours.Count)
                {
                    Text("More", NameX + 10f, y, NameW - 10f, rowH,
                        string.Format(UiText.NodeMore, t.neighbours.Count - shown), 10, Palette.SubtleText);
                    y += rowH;
                }

                Text("Message", NameX + 10f, y, NameW - 10f, rowH, string.Format(UiText.LayerMessage, t.bias.ToString("0.00")),
                    10, Color.white, true);
                Strip(t.message, ValueX, y, rowH, colour);
                Text("Length", ScoresX, y, HeadsW, rowH, string.Format(UiText.LayerLength, t.message_size.ToString("0.0")),
                    10, Palette.SubtleText);
                // Every edge type's message goes into the sum on the right.
                _edges.Add(new GraphEdges.Edge
                {
                    From = P(AttentionX + HeadsW + 10f, y + rowH / 2f), To = P(PipeX - 4f, StepY(1) + 29f),
                    Colour = colour.WithAlpha(0.7f), Width = 1.5f, Bend = -0.08f, Arrow = true,
                });
                y += rowH + LaneGap;
            }
        }

        static float Rows(List<LayerEdgeType> types, int perType) =>
            types.Sum(t => 2 + Mathf.Min(t.neighbours.Count, perType) + (t.neighbours.Count > perType ? 1 : 0));

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

        /// <summary>A vector as a row of cells in a frame of <paramref name="colour"/>, at (x, y) in a row of height h.</summary>
        void Strip(List<float> values, float x, float y, float h, Color colour, float w = StripW)
        {
            var frame = Ui.Box("Strip", _content, x, y + 2f, w, Mathf.Max(6f, h - 4f));
            Ui.Rounded(frame, colour, 3);
            Ui.Rounded(Ui.Stretch("Back", frame, 1.5f, 1.5f, 1.5f, 1.5f), Palette.Shadow, 2);
            if (values == null || values.Count == 0) return;
            var cells = Ui.Stretch("Cells", frame, 1.5f, 1.5f, 1.5f, 1.5f).gameObject;
            cells.AddComponent<CanvasRenderer>();
            var glyph = cells.AddComponent<EmbeddingGlyph>();
            glyph.raycastTarget = false;
            glyph.Horizontal = true;
            glyph.Set(values, values.Max(v => Mathf.Abs(v)));
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
