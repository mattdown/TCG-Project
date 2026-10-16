using System.Collections.Generic;
using Tcg.Protocol;
using Tcg.View;
using TMPro;
using UnityEngine;
using UnityEngine.UI;

namespace Tcg.Board
{
    /// <summary>
    /// The landscape board (docs/client-design.md, "Layout"), designed at 1280x720. Renders a
    /// server state as it is: card GameObjects are keyed by uid so they survive zone changes.
    /// </summary>
    public class BoardView : MonoBehaviour
    {
        const float FieldScale = 0.86f;
        const float RowGap = 14f;
        const float MaxRowWidth = 1180f;
        const float HandStep = 118f;
        const float HandMaxWidth = 700f;
        const float BackStep = 40f;

        [Tooltip("The server doesn't send the winning VP yet (docs/client-protocol.md: 20 wins).")]
        public int VpToWin = 20;

        [Header("Cards")]
        public CardView CardPrefab;
        public RectTransform OpponentUnits, HumanUnits, Hand, OpponentBacks;
        public GameObject CardBackTemplate;

        [Header("Opponent bar")]
        public TMP_Text OpponentAvatarText;
        public TMP_Text OpponentInfoText;
        public RectTransform OpponentVpFill;
        public TMP_Text OpponentVpText;
        public RectTransform OpponentGems;
        public TMP_Text OpponentEnergyText;

        [Header("Your side")]
        public TMP_Text HumanInfoText;
        public RectTransform HumanVpFill;
        public TMP_Text HumanVpText;
        public RectTransform HumanGems;
        public TMP_Text HumanEnergyText;
        public TMP_Text TurnText;
        public Button EndTurnButton;
        public TMP_Text EndTurnLabel;

        [Header("Messages")]
        public TMP_Text MessageText;
        public GameObject GameOverPanel;
        public TMP_Text GameOverText;

        readonly Dictionary<int, CardView> _cards = new Dictionary<int, CardView>();
        readonly List<GameObject> _backs = new List<GameObject>();
        float _opponentVpWidth, _humanVpWidth;

        void Awake()
        {
            _opponentVpWidth = OpponentVpFill.sizeDelta.x;
            _humanVpWidth = HumanVpFill.sizeDelta.x;
            CardBackTemplate.SetActive(false);
            GameOverPanel.SetActive(false);
            ShowMessage(UiText.Connecting);
        }

        public void Render(GameState s, IReadOnlyDictionary<string, CardDef> defs, string opponentName)
        {
            var human = s.Human;
            var opponent = s.Opponent;
            var playable = new HashSet<int>();
            foreach (var a in s.legal_actions)
                if (a.type == ActionTypes.Play && a.card.HasValue) playable.Add(a.card.Value);

            var seen = new HashSet<int>();
            LayoutRow(OpponentUnits, opponent.play, defs, seen);
            LayoutRow(HumanUnits, human.play, defs, seen);
            LayoutHand(human.hand ?? new List<CardInstance>(), defs, playable, seen);
            RemoveCardsNotIn(seen);
            LayoutBacks(opponent.hand_count);

            OpponentAvatarText.text = Initials(opponentName);
            OpponentInfoText.text = $"{opponentName} <color=#B8C6E8>· {UiText.Deck} {opponent.deck_count} · {UiText.Hand} {opponent.hand_count}</color>";
            SetVp(OpponentVpFill, _opponentVpWidth, OpponentVpText, opponent.vp);
            SetGems(OpponentGems, OpponentEnergyText, opponent);

            HumanInfoText.text = $"{UiText.You}\n<size=12><color=#B8C6E8>{UiText.Deck} {human.deck_count}</color></size>";
            SetVp(HumanVpFill, _humanVpWidth, HumanVpText, human.vp);
            SetGems(HumanGems, HumanEnergyText, human);
            TurnText.text = $"{UiText.Turn} {s.turn}";

            GameOverPanel.SetActive(s.game_over);
            if (s.game_over)
                GameOverText.text = s.winner == null ? UiText.Draw
                    : s.winner == s.human_seat ? UiText.YouWin : UiText.YouLose;
        }

        public void SetEndTurnButton(string label, bool interactable)
        {
            EndTurnLabel.text = label;
            EndTurnButton.interactable = interactable;
        }

        /// <summary>A one-line notice (server errors, connection problems); null or empty hides it.</summary>
        public void ShowMessage(string text)
        {
            MessageText.text = text ?? "";
            MessageText.transform.parent.gameObject.SetActive(!string.IsNullOrEmpty(text));
        }

        // --- cards

        CardView CardFor(CardInstance c, IReadOnlyDictionary<string, CardDef> defs, RectTransform parent)
        {
            if (!_cards.TryGetValue(c.uid, out var view))
            {
                view = Instantiate(CardPrefab, parent);
                view.name = $"Card {c.uid}";
                _cards[c.uid] = view;
            }
            else if (view.transform.parent != parent)
            {
                view.transform.SetParent(parent, false);
            }
            if (defs.TryGetValue(c.card_id, out var def)) view.Bind(def, c);
            else Debug.LogWarning($"Unknown card_id {c.card_id}");
            return view;
        }

        void LayoutRow(RectTransform row, List<CardInstance> units, IReadOnlyDictionary<string, CardDef> defs, HashSet<int> seen)
        {
            int n = units.Count;
            float slot = CardView.Width * FieldScale;
            float width = n * slot + (n - 1) * RowGap;
            float fit = width > MaxRowWidth ? MaxRowWidth / width : 1f;
            for (int i = 0; i < n; i++)
            {
                var view = CardFor(units[i], defs, row);
                seen.Add(units[i].uid);
                view.SetMark(CardMark.None);
                var rt = view.Rect;
                rt.localScale = Vector3.one * FieldScale * fit;
                rt.localRotation = Quaternion.identity;
                rt.anchoredPosition = new Vector2((i - (n - 1) / 2f) * (slot + RowGap) * fit, 0f);
                rt.SetSiblingIndex(i);
            }
        }

        void LayoutHand(List<CardInstance> hand, IReadOnlyDictionary<string, CardDef> defs, HashSet<int> playable, HashSet<int> seen)
        {
            int n = hand.Count;
            float step = n > 1 ? Mathf.Min(HandStep, (HandMaxWidth - CardView.Width) / (n - 1)) : 0f;
            for (int i = 0; i < n; i++)
            {
                var view = CardFor(hand[i], defs, Hand);
                seen.Add(hand[i].uid);
                view.SetMark(playable.Contains(hand[i].uid) ? CardMark.Playable : CardMark.None);
                // The fan pivots each card on its bottom centre, which sits on a shallow arc; the
                // arc follows x so a big, tightly packed hand doesn't curl off the screen.
                float x = (i - (n - 1) / 2f) * step;
                float u = x / HandStep;
                float angle = -u * 4f;
                var bottom = new Vector2(x, -26f - u * u * 6f);
                float rad = angle * Mathf.Deg2Rad;
                var centre = bottom + new Vector2(-Mathf.Sin(rad), Mathf.Cos(rad)) * (CardView.Height / 2f);
                var rt = view.Rect;
                rt.localScale = Vector3.one;
                rt.localRotation = Quaternion.Euler(0f, 0f, angle);
                rt.anchoredPosition = centre;
                rt.SetSiblingIndex(i);
            }
        }

        void RemoveCardsNotIn(HashSet<int> seen)
        {
            var gone = new List<int>();
            foreach (var kv in _cards)
                if (!seen.Contains(kv.Key)) gone.Add(kv.Key);
            foreach (int uid in gone)
            {
                Destroy(_cards[uid].gameObject);
                _cards.Remove(uid);
            }
        }

        void LayoutBacks(int count)
        {
            while (_backs.Count < count)
            {
                var back = Instantiate(CardBackTemplate, OpponentBacks);
                back.SetActive(true);
                _backs.Add(back);
            }
            for (int i = 0; i < _backs.Count; i++)
            {
                bool shown = i < count;
                _backs[i].SetActive(shown);
                if (!shown) continue;
                float off = i - (count - 1) / 2f;
                var rt = (RectTransform)_backs[i].transform;
                rt.anchoredPosition = new Vector2(off * BackStep, 0f);
                rt.localRotation = Quaternion.Euler(0f, 0f, off * 4f);
            }
        }

        // --- HUD

        void SetVp(RectTransform fill, float fullWidth, TMP_Text label, int vp)
        {
            float t = Mathf.Clamp01(VpToWin > 0 ? vp / (float)VpToWin : 0f);
            fill.sizeDelta = new Vector2(fullWidth * t, fill.sizeDelta.y);
            fill.gameObject.SetActive(t > 0f);
            label.text = $"{vp}/{VpToWin}";
        }

        static void SetGems(RectTransform gems, TMP_Text label, PlayerState p)
        {
            var template = gems.GetChild(0).gameObject;
            while (gems.childCount < p.energy_total)
                Instantiate(template, gems);
            for (int i = 0; i < gems.childCount; i++)
            {
                var gem = gems.GetChild(i);
                gem.gameObject.SetActive(i < p.energy_total);
                bool ready = i < p.energy_ready;
                gem.GetChild(0).GetComponent<Image>().color = ready ? Palette.Energy : Palette.EnergySpent;
                if (gem.childCount > 2) gem.GetChild(2).gameObject.SetActive(ready);
            }
            label.text = $"{p.energy_ready}/{p.energy_total}";
        }

        static string Initials(string name)
        {
            if (string.IsNullOrEmpty(name)) return "?";
            return name.Length <= 2 ? name.ToUpperInvariant() : name.Substring(0, 2).ToUpperInvariant();
        }
    }
}
