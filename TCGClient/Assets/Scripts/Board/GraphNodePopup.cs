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
    /// One node of the GNN overlay in depth (the server's graph_node), drawn as a schematic read left
    /// to right: the node's named input features, the stages that make its first embedding, then one
    /// box per GNN layer between its vectors, and the head slots that read the final one. Under each
    /// layer, a table of what it takes in: a row per edge type with a bar for the size of that type's
    /// message, and below it a row per neighbour with the attention it gets.
    /// </summary>
    public class GraphNodePopup : MonoBehaviour
    {
        const float W = 1120f, H = 630f;
        const float BandY = 165f;           // the pipeline's centre line, from the top
        const float VectorW = 16f, VectorH = 112f;
        const float FirstX = 400f, LastX = 940f;  // the first and final embeddings' columns
        const float TableTop = 300f, MaxRowH = 16f, MinRowH = 13f, TypeGap = 4f;
        const float LayerBoxH = 66f;

        RectTransform _content;
        GraphEdges _lines;
        readonly List<GraphEdges.Edge> _edges = new List<GraphEdges.Edge>();
        Func<int, string> _nameOf;
        Func<string, Color> _nodeColour, _edgeColour;

        public bool IsOpen => gameObject.activeSelf;

        public static GraphNodePopup Create(RectTransform parent, Func<int, string> nameOf,
            Func<string, Color> nodeColour, Func<string, Color> edgeColour)
        {
            var root = Ui.Stretch("NodePopup", parent, 0, 0, 0, 0);
            var view = root.gameObject.AddComponent<GraphNodePopup>();
            view._nameOf = nameOf;
            view._nodeColour = nodeColour;
            view._edgeColour = edgeColour;
            Ui.Scrim(root, "Scrim", 0.55f).onClick.AddListener(view.Hide);
            var card = Ui.Node("Card", root);
            Ui.Anchor(card, new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), Vector2.zero, new Vector2(W, H));
            Ui.Panel(card, 16, null, 1f).raycastTarget = true;  // opaque: the overlay's panels sit behind it
            view._content = Ui.Stretch("Content", card, 0, 0, 0, 0);
            var close = Ui.Node("Close", card);
            Ui.Anchor(close, new Vector2(1, 1), new Vector2(1, 1), new Vector2(-16, -14), new Vector2(96, 34));
            Ui.Button(close, UiText.NodeClose, Palette.Muted, 14, out _).onClick.AddListener(view.Hide);
            root.gameObject.SetActive(false);
            return view;
        }

        public void Hide() => gameObject.SetActive(false);

        public void Show(GraphNodeDetail node)
        {
            for (int i = _content.childCount - 1; i >= 0; i--) Destroy(_content.GetChild(i).gameObject);
            _edges.Clear();
            var lines = Ui.Stretch("Lines", _content, 0, 0, 0, 0).gameObject;
            lines.AddComponent<CanvasRenderer>();
            _lines = lines.AddComponent<GraphEdges>();
            _lines.raycastTarget = false;

            gameObject.SetActive(true);
            transform.SetAsLastSibling();
            BuildHeader(node);
            if (node.embedding != "gnn" || node.layers == null || node.layers.Count == 0)
            {
                BuildInputs(node, 0);
            }
            else
            {
                BuildInputs(node, FirstX);
                float step = (LastX - FirstX) / node.layers.Count;
                for (int i = 0; i < node.layers.Count; i++)
                    BuildLayer(node, i, FirstX + i * step, FirstX + (i + 1) * step);
                BuildHeads(node);
                BuildTable(node, step);
                Text("Footnote", 24, H - 26, W - 48, 16, UiText.NodeFootnote, 10, Palette.SubtleText);
            }
            _lines.Set(_edges);
        }

        // --- header

        void BuildHeader(GraphNodeDetail node)
        {
            var title = Ui.Display(Ui.Box("Title", _content, 24, 14, W - 160, 28), _nameOf(node.id), 22,
                TextAlignmentOptions.Left);
            title.overflowMode = TextOverflowModes.Ellipsis;
            Ui.Rounded(Ui.Box("Swatch", _content, 24, 50, 10, 10), _nodeColour(node.type), 5);
            string readBy = node.read_by != null && node.read_by.Count > 0 ? string.Join(", ", node.read_by) : UiText.NodeReadByNothing;
            string subtitle = node.embedding == "gnn"
                ? string.Format(UiText.NodeSubtitle, node.type, node.hidden, node.layers.Count, readBy)
                : string.Format(UiText.NodeNoModel, node.type);
            Text("Subtitle", 40, 46, W - 200, 18, subtitle, 12, Palette.SubtleText);
        }

        // --- inputs and the first embedding

        /// <summary>The feature boxes, then (with a model) the stages up to the first embedding at x = <paramref name="h0"/>.</summary>
        void BuildInputs(GraphNodeDetail node, float h0)
        {
            var groups = node.input ?? new List<FeatureGroup>();
            bool card = groups.Count == 2;
            float boxW = h0 > 0 ? (card ? 150f : 210f) : 320f, top = 74f, bottom = 280f;
            float gap = 10f, boxH = (bottom - top - gap * (groups.Count - 1)) / Mathf.Max(1, groups.Count);
            var boxes = new List<Rect>();
            for (int g = 0; g < groups.Count; g++)
                boxes.Add(FeatureBox(groups[g], 24, top + g * (boxH + gap), boxW, boxH));
            if (h0 <= 0) return;

            var stages = node.stages ?? new List<GraphStage>();
            var first = stages.Count > 0 ? stages[stages.Count - 1] : null;
            Vector(first?.vector, first?.dim ?? 0, h0, BandY, VectorH, _nodeColour(node.type));
            if (card && stages.Count == 3)
            {
                // static → MLP → encoder vector; joined with dynamic (concat) → linear → first embedding
                var s = boxes[0];
                float encX = 240f, catX = 320f;
                Vector(stages[0].vector, stages[0].dim, encX, s.center.y, 60f, _nodeColour(node.type));
                Arrow(new Vector2(s.xMax, s.center.y), new Vector2(encX - VectorW / 2f - 2f, s.center.y), Op("mlp"));
                ConcatBar(catX, stages[1].dim);
                Arrow(new Vector2(encX + VectorW / 2f, s.center.y), new Vector2(catX - 6f, BandY - 20f), null);
                var d = boxes[1];
                Arrow(new Vector2(d.xMax, d.center.y), new Vector2(catX - 6f, BandY + 20f), null);
                Arrow(new Vector2(catX + 6f, BandY), new Vector2(h0 - VectorW / 2f - 2f, BandY), Op(stages[2].op));
            }
            else
            {
                foreach (var b in boxes)
                    Arrow(new Vector2(b.xMax, b.center.y), new Vector2(h0 - VectorW / 2f - 2f, BandY),
                        first != null ? Op(first.op) : null);
            }
        }

        Rect FeatureBox(FeatureGroup group, float x, float y, float w, float h)
        {
            var box = Ui.Box($"Input {group.name}", _content, x, y, w, h);
            Ui.Rounded(box, Color.white.WithAlpha(0.05f), 8);
            Text("Header", 8, 5, w - 16, 15, string.Format(UiText.NodeGroup, group.name, group.dim), 11, Color.white,
                true, box);
            var features = group.features ?? new List<NamedValue>();
            int fits = Mathf.Max(1, Mathf.FloorToInt((h - 24f) / 13f));
            int shown = features.Count > fits ? fits - 1 : features.Count;
            for (int i = 0; i < shown; i++)
            {
                Text("Name", 8, 22 + i * 13, w - 56, 13, features[i].name, 10, Palette.LanternText, false, box);
                Text("Value", w - 52, 22 + i * 13, 44, 13, features[i].value.ToString("0.###"), 10, Palette.SubtleText,
                    false, box, TextAlignmentOptions.Right);
            }
            if (features.Count == 0)
                Text("Zero", 8, 22, w - 16, 13, UiText.NodeAllZero, 10, Palette.SubtleText, false, box);
            else if (shown < features.Count)
                Text("More", 8, 22 + shown * 13, w - 16, 13, string.Format(UiText.NodeMore, features.Count - shown), 10,
                    Palette.SubtleText, false, box);
            return new Rect(x, y, w, h);
        }

        void ConcatBar(float x, int dim)
        {
            Ui.Rounded(Ui.Box("Concat", _content, x - 6f, BandY - VectorH / 2f, 12f, VectorH), Color.white.WithAlpha(0.18f), 4);
            DimLabel(x, BandY + VectorH / 2f, dim);
            Text("ConcatOp", x - 40f, BandY - VectorH / 2f - 18f, 80f, 14f, Op("concat"), 10, Palette.SubtleText, false,
                null, TextAlignmentOptions.Center);
        }

        // --- layers

        void BuildLayer(GraphNodeDetail node, int index, float fromX, float toX)
        {
            var layer = node.layers[index];
            float boxX = (fromX + toX) / 2f, boxW = toX - fromX - VectorW - 26f;
            var box = Ui.Box($"Layer {index + 1}", _content, boxX - boxW / 2f, BandY - LayerBoxH / 2f, boxW, LayerBoxH);
            Ui.Rounded(box, Palette.Lantern.WithAlpha(0.08f), 8);
            Ui.Rim(Ui.Stretch("Rim", box, 0, 0, 0, 0), Palette.Lantern.WithAlpha(0.5f), 8);
            Text("Name", 4, 5, boxW - 8, 14, string.Format(UiText.NodeLayer, index + 1), 11, Color.white, true, box,
                TextAlignmentOptions.Center);
            var ops = Text("Ops", 4, 20, boxW - 8, 42, string.Format(UiText.NodeLayerOps, node.heads), 9,
                Palette.SubtleText, false, box, TextAlignmentOptions.Center);
            ops.textWrappingMode = TextWrappingModes.Normal;

            bool last = index == node.layers.Count - 1;
            Vector(layer.vector, layer.dim, toX, BandY, VectorH, _nodeColour(node.type));
            if (last)
                Text("Final", toX - 40f, BandY - VectorH / 2f - 18f, 80f, 14f, UiText.NodeFinal, 10, Palette.SubtleText,
                    false, null, TextAlignmentOptions.Center);
            Arrow(new Vector2(fromX + VectorW / 2f + 2f, BandY), new Vector2(boxX - boxW / 2f - 2f, BandY), null);
            Arrow(new Vector2(boxX + boxW / 2f, BandY), new Vector2(toX - VectorW / 2f - 2f, BandY), null);
            // The residual: the layer adds its messages to the node's own embedding.
            _edges.Add(new GraphEdges.Edge
            {
                From = P(fromX, BandY - VectorH / 2f + 6f), To = P(toX, BandY - VectorH / 2f + 6f),
                Colour = Color.white.WithAlpha(0.3f), Width = 1.2f, Bend = 0.18f, Inset = 0f, Arrow = true,
            });
            // Messages come up from the table into the layer.
            _edges.Add(new GraphEdges.Edge
            {
                From = P(boxX, TableTop - 4f), To = P(boxX, BandY + LayerBoxH / 2f + 2f),
                Colour = Palette.Lantern.WithAlpha(0.7f), Width = 2f, Arrow = true,
            });
        }

        void BuildHeads(GraphNodeDetail node)
        {
            if (node.read_by == null) return;
            float x = LastX + 36f, y = BandY - node.read_by.Count * 13f;
            for (int i = 0; i < node.read_by.Count; i++)
            {
                var chip = Ui.Box("Head", _content, x, y + i * 26f, 116f, 22f);
                Ui.Rounded(chip, Color.white.WithAlpha(0.07f), 11);
                Text("Text", 6, 3, 104, 16, node.read_by[i], 10, Palette.LanternText, false, chip,
                    TextAlignmentOptions.Center);
                Arrow(new Vector2(LastX + VectorW / 2f + 2f, BandY), new Vector2(x - 2f, y + i * 26f + 11f), null);
            }
        }

        // --- messages table

        void BuildTable(GraphNodeDetail node, float step)
        {
            Text("Messages", 24, TableTop - 4f, FirstX - 40f, 58f, UiText.NodeMessages, 10, Palette.SubtleText)
                .textWrappingMode = TextWrappingModes.Normal;
            // Edge types in the first layer's order; the neighbours are the same at every layer.
            var types = node.layers[0].incoming.Select(m => m.type).ToList();
            if (types.Count == 0) return;
            // Every neighbour if they fit (rows shrinking to MinRowH first), else the most per type that do.
            float y = TableTop + 60f, room = H - 34f - y - TypeGap * types.Count;
            int perType = types.Max(t => node.layers[0].incoming.First(m => m.type == t).neighbours.Count);
            while (perType > 1 && room / Rows(node, types, perType) < MinRowH) perType--;
            float rowH = Mathf.Min(MaxRowH, room / Rows(node, types, perType));
            float cellW = step - 24f, barW = cellW - 40f;
            foreach (var type in types)
            {
                var first = node.layers[0].incoming.First(m => m.type == type);
                var colour = _edgeColour(first.shown_as);
                Ui.Img(Ui.Box("Swatch", _content, 24, y + 6f, 16, 4), null, colour);
                string label = first.shown_as == type ? Name(type)
                    : string.Format(UiText.NodeReverse, Name(type), Name(first.shown_as));
                Text("Type", 46, y, FirstX - 70f, rowH, label, 11, Color.white, true);
                for (int l = 0; l < node.layers.Count; l++)
                {
                    var incoming = node.layers[l].incoming;
                    var m = incoming.FirstOrDefault(x => x.type == type);
                    if (m == null) continue;
                    float max = Mathf.Max(1e-4f, incoming.Max(x => x.message));
                    float cx = FirstX + (l + 0.5f) * step - cellW / 2f;
                    // The bar is relative to the layer's biggest message; the number beside it is the size itself.
                    Ui.Rounded(Ui.Box("Bar", _content, cx, y + 3f, barW * Mathf.Clamp01(m.message / max), rowH - 6f),
                        colour, 3);
                    Text("Size", cx + barW, y, cellW - barW, rowH, m.message.ToString("0.0"), 9, Palette.SubtleText,
                        false, null, TextAlignmentOptions.Right);
                }
                y += rowH;

                // The neighbours with the most attention on average over the layers.
                var order = first.neighbours.Select(n => n.node)
                    .OrderByDescending(id => node.layers.Average(l => Attention(l, type, id))).ToList();
                int shown = order.Count > perType ? perType : order.Count;
                for (int k = 0; k < shown; k++)
                {
                    Text("Neighbour", 46, y, FirstX - 70f, rowH, "← " + _nameOf(order[k]), 10, Palette.LanternText);
                    for (int l = 0; l < node.layers.Count; l++)
                    {
                        float a = Attention(node.layers[l], type, order[k]);
                        float cx = FirstX + (l + 0.5f) * step - cellW / 2f;
                        Ui.Rounded(Ui.Box("Cell", _content, cx, y + 1f, cellW, rowH - 2f),
                            Palette.Lantern.WithAlpha(0.06f + 0.6f * a), 3);
                        Text("Attention", cx, y, cellW, rowH, a.ToString("0.00"), 9, Color.white, false, null,
                            TextAlignmentOptions.Center);
                    }
                    y += rowH;
                }
                if (shown < order.Count)
                {
                    Text("More", 46, y, FirstX - 70f, rowH, string.Format(UiText.NodeMore, order.Count - shown), 10,
                        Palette.SubtleText);
                    y += rowH;
                }
                y += TypeGap;
            }
        }

        static int Rows(GraphNodeDetail node, List<string> types, int perType) =>
            types.Sum(t =>
            {
                int n = node.layers[0].incoming.First(m => m.type == t).neighbours.Count;
                return 1 + Mathf.Min(n, perType) + (n > perType ? 1 : 0);
            });

        static float Attention(GraphLayer layer, string type, int node)
        {
            var m = layer.incoming.FirstOrDefault(x => x.type == type);
            var n = m?.neighbours.FirstOrDefault(x => x.node == node);
            return n?.attention ?? 0f;
        }

        // --- drawing helpers

        /// <summary>A vector as a column of cells, centred on (x, y), with its size under it.</summary>
        void Vector(List<float> values, int dim, float x, float y, float height, Color colour)
        {
            var frame = Ui.Box("Vector", _content, x - VectorW / 2f - 2f, y - height / 2f - 2f, VectorW + 4f, height + 4f);
            Ui.Rounded(frame, colour, 4);
            Ui.Rounded(Ui.Stretch("Back", frame, 2, 2, 2, 2), Palette.Shadow, 3);
            if (values != null && values.Count > 0)
            {
                var cells = Ui.Stretch("Cells", frame, 2, 2, 2, 2).gameObject;
                cells.AddComponent<CanvasRenderer>();
                var glyph = cells.AddComponent<EmbeddingGlyph>();
                glyph.raycastTarget = false;
                glyph.Set(values, values.Max(v => Mathf.Abs(v)));
            }
            DimLabel(x, y + height / 2f, dim);
        }

        void DimLabel(float x, float y, int dim) =>
            Text("Dim", x - 30f, y + 4f, 60f, 14f, dim.ToString(), 10, Palette.SubtleText, false, null,
                TextAlignmentOptions.Center);

        /// <summary>An arrow between two points (from the top-left), with an optional label over its middle.</summary>
        void Arrow(Vector2 from, Vector2 to, string label)
        {
            _edges.Add(new GraphEdges.Edge
            {
                From = P(from.x, from.y), To = P(to.x, to.y), Colour = Color.white.WithAlpha(0.55f), Width = 1.5f,
                Arrow = true,
            });
            if (label != null)
            {
                var mid = (from + to) / 2f;
                Text("Op", mid.x - 30f, mid.y - 16f, 60f, 13f, label, 9, Palette.Lantern, true, null,
                    TextAlignmentOptions.Center);
            }
        }

        static string Op(string op) => op == "mlp" ? "MLP" : op;

        static string Name(string type) => type.Replace('_', ' ');

        /// <summary>A point given from the panel's top-left, in the line graphic's centred space.</summary>
        static Vector2 P(float x, float y) => new Vector2(x - W / 2f, H / 2f - y);

        TextMeshProUGUI Text(string name, float x, float y, float w, float h, string text, float size, Color colour,
            bool bold = false, RectTransform parent = null, TextAlignmentOptions align = TextAlignmentOptions.Left)
        {
            var t = Ui.Text(Ui.Box(name, parent != null ? parent : _content, x, y, w, h), text,
                bold ? Ui.Theme.BodyBold : Ui.Theme.Body, size, colour, align);
            t.overflowMode = TextOverflowModes.Ellipsis;
            return t;
        }
    }
}
