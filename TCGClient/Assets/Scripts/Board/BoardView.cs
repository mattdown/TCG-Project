using System.Collections;
using System.Collections.Generic;
using DG.Tweening;
using Tcg.Protocol;
using Tcg.View;
using TMPro;
using UnityEngine;
using UnityEngine.UI;

namespace Tcg.Board
{
    /// <summary>
    /// The landscape board (docs/client-design.md, "Layout"), designed at 1280x720. Renders a
    /// server state as it is: card GameObjects are keyed by uid so they survive zone changes, and
    /// what an action did (damage, defeats, VP, cards moving) is animated from the action
    /// record's result, as the server reports it.
    /// </summary>
    public class BoardView : MonoBehaviour
    {
        const float FieldScale = 0.86f;
        const float RowGap = 14f;
        const float MaxRowWidth = 1180f;
        const float HandStep = 118f;
        const float HandMaxWidth = 700f;
        const float BackStep = 40f;
        const float Move = 0.3f;

        public UiTheme Theme;

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

        /// <summary>Gets taps and drags from every card on the board.</summary>
        public ICardInputHandler InputHandler { get; set; }
        public GameState State { get; private set; }
        public IReadOnlyDictionary<string, CardDef> Defs { get; private set; }
        public string OpponentName { get; private set; } = "";
        public RectTransform Root => (RectTransform)transform;
        public int VpToWin => State != null && State.vp_to_win > 0 ? State.vp_to_win : 20;

        /// <summary>Above the cards: dragged cards, arrows and effects.</summary>
        public RectTransform TopLayer { get; private set; }

        readonly Dictionary<int, CardView> _cards = new Dictionary<int, CardView>();
        readonly Dictionary<int, string> _zoneOf = new Dictionary<int, string>();
        readonly Dictionary<int, Vector3> _spawnAt = new Dictionary<int, Vector3>();
        readonly List<GameObject> _backs = new List<GameObject>();
        float _opponentVpWidth, _humanVpWidth;
        RectTransform _ghost, _vpGain, _dashedGem;
        CanvasGroup _handGroup;
        int _ghostSlots;

        void Awake()
        {
            Ui.Theme = Theme;
            _opponentVpWidth = OpponentVpFill.sizeDelta.x;
            _humanVpWidth = HumanVpFill.sizeDelta.x;
            CardBackTemplate.SetActive(false);
            _handGroup = Hand.gameObject.AddComponent<CanvasGroup>();

            TopLayer = Ui.Stretch("Top", Root, 0, 0, 0, 0);
            TopLayer.SetSiblingIndex(MessageText.transform.parent.GetSiblingIndex());

            _ghost = Ui.Node("Ghost", HumanUnits);
            _ghost.sizeDelta = new Vector2(CardView.Width * FieldScale, CardView.Height * FieldScale);
            Ui.Rounded(_ghost, Color.white.WithAlpha(0.28f), 12);
            _ghost.gameObject.SetActive(false);

            var track = HumanVpFill.parent;
            _vpGain = Ui.Box("Gain", track, 2, 2, 0, HumanVpFill.sizeDelta.y);
            Ui.Img(_vpGain, Theme.Stripes, Color.white).type = Image.Type.Tiled;
            _vpGain.SetSiblingIndex(HumanVpFill.GetSiblingIndex());
            _vpGain.gameObject.SetActive(false);

            _dashedGem = Ui.Node("NewGem", HumanGems.parent);
            _dashedGem.sizeDelta = ((RectTransform)HumanGems.GetChild(0)).sizeDelta;
            Ui.Img(Ui.Stretch("Fill", _dashedGem, 0, 0, 0, 0), Theme.GemFill, Palette.Energy.WithAlpha(0.35f));
            Ui.Img(Ui.Stretch("Rim", _dashedGem, 0, 0, 0, 0), Theme.GemDashed, Color.white);
            _dashedGem.SetSiblingIndex(HumanGems.GetSiblingIndex() + 1);
            _dashedGem.gameObject.SetActive(false);

            ShowMessage(UiText.Connecting);
        }

        // --- rendering

        /// <summary>
        /// Shows <paramref name="s"/>. With <paramref name="animate"/>, cards move to their new places
        /// and <paramref name="result"/> (what the last action did) is played out first.
        /// </summary>
        public void Render(GameState s, IReadOnlyDictionary<string, CardDef> defs, string opponentName, bool animate,
            ActionResult result = null)
        {
            var previous = State;
            if (animate && previous != null && result != null) PlayResult(result, previous.human_seat);
            State = s;
            Defs = defs;
            OpponentName = opponentName;
            animate &= previous != null;
            var human = s.Human;
            var opponent = s.Opponent;
            var playable = new HashSet<int>();
            foreach (var a in s.legal_actions)
                if (a.type == ActionTypes.Play && a.card.HasValue) playable.Add(a.card.Value);

            var seen = new HashSet<int>();
            LayoutRow(OpponentUnits, opponent.play, "opponent_play", seen, animate, 0);
            LayoutRow(HumanUnits, human.play, "human_play", seen, animate, _ghostSlots);
            LayoutHand(human.hand ?? new List<CardInstance>(), playable, seen, animate);
            RemoveCardsNotIn(seen, animate);
            LayoutBacks(opponent.hand_count);
            _handGroup.alpha = s.InMulligan ? 0f : 1f;
            _handGroup.blocksRaycasts = !s.InMulligan;

            OpponentAvatarText.text = Initials(opponentName);
            OpponentInfoText.text = $"{opponentName} <color=#B8C6E8>· {UiText.Deck} {opponent.deck_count} · {UiText.Hand} {opponent.hand_count}</color>";
            SetVp(OpponentVpFill, _opponentVpWidth, OpponentVpText, opponent.vp, animate);
            SetGems(OpponentGems, OpponentEnergyText, opponent);

            HumanInfoText.text = $"{UiText.You}\n<size=12><color=#B8C6E8>{UiText.Deck} {human.deck_count}</color></size>";
            SetVp(HumanVpFill, _humanVpWidth, HumanVpText, human.vp, animate);
            SetGems(HumanGems, HumanEnergyText, human);
            TurnText.text = $"{UiText.Turn} {s.turn}";
        }

        /// <summary>Re-lays out the current state, e.g. to snap a dropped card back.</summary>
        public void Relayout()
        {
            if (State != null) Render(State, Defs, OpponentName, true);
        }

        public CardView CardByUid(int uid) => _cards.TryGetValue(uid, out var v) ? v : null;

        public bool IsInHumanHand(int uid) => Zone(uid) == "hand";
        public bool IsHumanUnit(int uid) => Zone(uid) == "human_play";
        public bool IsOpponentUnit(int uid) => Zone(uid) == "opponent_play";
        string Zone(int uid) => _zoneOf.TryGetValue(uid, out var z) ? z : null;

        public IEnumerable<CardView> OpponentUnitViews()
        {
            if (State == null) yield break;
            foreach (var c in State.Opponent.play)
                if (_cards.TryGetValue(c.uid, out var v)) yield return v;
        }

        /// <summary>A point in TopLayer space for a world position.</summary>
        public Vector2 ToTop(Vector3 world) => TopLayer.InverseTransformPoint(world);

        public void SetEndTurnButton(string label, bool interactable)
        {
            EndTurnLabel.text = label;
            EndTurnButton.interactable = interactable;
        }

        /// <summary>A one-line notice (server errors, connection problems); null or empty hides it.</summary>
        public void ShowMessage(string text)
        {
            var box = MessageText.transform.parent;
            MessageText.text = text ?? "";
            box.gameObject.SetActive(!string.IsNullOrEmpty(text));
            if (!string.IsNullOrEmpty(text)) box.SetAsLastSibling();
        }

        // --- drag previews

        /// <summary>A light slot at the end of your row where a played card will land.</summary>
        public void ShowGhostSlot(bool show)
        {
            int slots = show ? 1 : 0;
            if (slots == _ghostSlots || State == null) return;
            _ghostSlots = slots;
            _ghost.gameObject.SetActive(show);
            LayoutRow(HumanUnits, State.Human.play, "human_play", new HashSet<int>(), true, _ghostSlots);
        }

        /// <summary>Outlines the ready gems a play would spend; 0 clears it.</summary>
        public void PreviewEnergySpend(int spend)
        {
            var p = State.Human;
            for (int i = 0; i < HumanGems.childCount; i++)
            {
                var rim = HumanGems.GetChild(i).GetChild(1);
                bool spent = i < spend && i < p.energy_ready;
                rim.GetComponent<Image>().color = spent ? Color.white : Palette.Outline;
                rim.localScale = Vector3.one * (spent ? 1.1f : 1f);
            }
            HumanEnergyText.text = spend > 0
                ? $"{p.energy_ready} → {p.energy_ready - spend}"
                : $"{p.energy_ready}/{p.energy_total}";
        }

        /// <summary>A dashed gem slot at the end of your energy bar.</summary>
        public void PreviewNewGem(bool show) => _dashedGem.gameObject.SetActive(show);

        /// <summary>Stripes on your VP bar for the VP a score would add; 0 clears it.</summary>
        public void PreviewVp(int gain)
        {
            int vp = State.Human.vp;
            _vpGain.gameObject.SetActive(gain > 0);
            float t = Mathf.Clamp01((vp + gain) / (float)VpToWin);
            _vpGain.sizeDelta = new Vector2(_humanVpWidth * t, _vpGain.sizeDelta.y);
            HumanVpText.text = gain > 0 ? $"{vp} → {vp + gain}" : $"{vp}/{VpToWin}";
        }

        // --- the opponent's actions

        /// <summary>What happens before the state changes: an arrow for a duel, a pulse for a score.</summary>
        public IEnumerator ShowAction(GameAction action, ArrowView arrow)
        {
            var actor = action.card.HasValue ? CardByUid(action.card.Value) : null;
            if (action.type == ActionTypes.Duel && actor != null && action.target.HasValue)
            {
                var target = CardByUid(action.target.Value);
                if (target == null) yield break;
                actor.SetMark(CardMark.Selected);
                target.SetTargetRing(TargetRing.Hovered);
                arrow.Show(ToTop(actor.Rect.position), ToTop(target.Rect.position), Palette.GlowTarget, true);
                yield return new WaitForSeconds(0.55f);
                arrow.Hide();
                actor.SetMark(CardMark.None);
                target.SetTargetRing(TargetRing.None);
            }
            else if (action.type == ActionTypes.Score && actor != null)
            {
                actor.SetMark(CardMark.Selected);
                yield return actor.Visual.DOPunchScale(Vector3.one * 0.15f, 0.4f, 6).WaitForCompletion();
                actor.SetMark(CardMark.None);
            }
        }

        // --- layout

        CardView CardFor(CardInstance c, RectTransform parent)
        {
            if (!_cards.TryGetValue(c.uid, out var view))
            {
                view = Instantiate(CardPrefab, parent);
                view.name = $"Card {c.uid}";
                view.Input.Handler = InputHandler;
                _cards[c.uid] = view;
            }
            else if (view.transform.parent != parent)
            {
                view.transform.SetParent(parent, true);
            }
            if (Defs.TryGetValue(c.card_id, out var def)) view.Bind(def, c);
            else Debug.LogWarning($"Unknown card_id {c.card_id}");
            return view;
        }

        void LayoutRow(RectTransform row, List<CardInstance> units, string zone, HashSet<int> seen, bool animate, int extraSlots)
        {
            int n = units.Count + extraSlots;
            float slot = CardView.Width * FieldScale;
            float width = n * slot + (n - 1) * RowGap;
            float fit = width > MaxRowWidth ? MaxRowWidth / width : 1f;
            for (int i = 0; i < units.Count; i++)
            {
                var c = units[i];
                bool known = _cards.ContainsKey(c.uid);
                var view = CardFor(c, row);
                seen.Add(c.uid);
                if (!known && animate && _spawnAt.TryGetValue(c.uid, out var from))
                {
                    view.Rect.position = from;  // e.g. played from the opponent's hand
                    view.Rect.localScale = Vector3.one * 0.4f;
                }
                var pos = new Vector2((i - (n - 1) / 2f) * (slot + RowGap) * fit, 0f);
                Place(view, pos, Vector3.one * FieldScale * fit, Quaternion.identity, animate);
                view.Rect.SetSiblingIndex(i);
                view.SetMark(CardMark.None);
                _zoneOf[c.uid] = zone;
            }
            if (extraSlots > 0)
            {
                _ghost.anchoredPosition = new Vector2((n - 1) / 2f * (slot + RowGap) * fit, 0f);
                _ghost.localScale = Vector3.one * fit;
            }
        }

        void LayoutHand(List<CardInstance> hand, HashSet<int> playable, HashSet<int> seen, bool animate)
        {
            int n = hand.Count;
            float step = n > 1 ? Mathf.Min(HandStep, (HandMaxWidth - CardView.Width) / (n - 1)) : 0f;
            for (int i = 0; i < n; i++)
            {
                var c = hand[i];
                bool known = _cards.ContainsKey(c.uid);
                var view = CardFor(c, Hand);
                seen.Add(c.uid);
                // The fan pivots each card on its bottom centre, which sits on a shallow arc; the
                // arc follows x so a big, tightly packed hand doesn't curl off the screen.
                float x = (i - (n - 1) / 2f) * step;
                float u = x / HandStep;
                float angle = -u * 4f;
                var bottom = new Vector2(x, -26f - u * u * 6f);
                float rad = angle * Mathf.Deg2Rad;
                var centre = bottom + new Vector2(-Mathf.Sin(rad), Mathf.Cos(rad)) * (CardView.Height / 2f);
                if (!known && animate && _spawnAt.TryGetValue(c.uid, out var from))
                    view.Rect.position = from;  // drawn: in from your deck
                Place(view, centre, Vector3.one, Quaternion.Euler(0f, 0f, angle), animate);
                view.Rect.SetSiblingIndex(i);
                view.SetMark(playable.Contains(c.uid) ? CardMark.Playable : CardMark.None);
                _zoneOf[c.uid] = "hand";
            }
        }

        static void Place(CardView view, Vector2 pos, Vector3 scale, Quaternion rotation, bool animate)
        {
            var rt = view.Rect;
            rt.DOKill();
            view.SetDimmed(false);
            view.SetTargetRing(TargetRing.None);
            view.SetBadge(null, Color.clear);
            if (!animate)
            {
                rt.anchoredPosition = pos;
                rt.localScale = scale;
                rt.localRotation = rotation;
                return;
            }
            rt.DOAnchorPos(pos, Move).SetEase(Ease.OutCubic);
            rt.DOScale(scale, Move).SetEase(Ease.OutCubic);
            rt.DOLocalRotateQuaternion(rotation, Move).SetEase(Ease.OutCubic);
        }

        /// <summary>
        /// Plays out an action's result before the new layout: damage and defeats on the cards
        /// involved, VP gains, and cards moving to energy, discard or from a deck or hidden hand.
        /// </summary>
        void PlayResult(ActionResult r, int humanSeat)
        {
            _spawnAt.Clear();
            foreach (var d in r.damage)
            {
                var view = CardByUid(d.uid);
                if (view == null || d.amount <= 0) continue;
                FloatText(view.Rect.position, $"-{d.amount}", Palette.Health);
                view.Visual.DOShakeAnchorPos(0.35f, 8f, 20);
            }
            foreach (var p in r.vp)
                if (p.amount > 0)
                    FloatText((p.player == humanSeat ? HumanVpText : OpponentVpText).transform.position, $"+{p.amount}", Palette.Gold);
            foreach (var m in r.moves)
            {
                bool human = m.player == humanSeat;
                var view = m.uid.HasValue ? CardByUid(m.uid.Value) : null;
                if (m.to == Zones.Energy)
                {
                    if (view != null) Leave(view, v => FlyInto(v, human ? HumanGems : OpponentGems));
                    else FlyCardBack(OpponentBacks, human ? HumanGems : OpponentGems);
                }
                else if (m.to == Zones.Discard && view != null)
                {
                    Leave(view, Defeat);
                }
                else if (m.from == Zones.Hand && m.to == Zones.Play && !human && m.uid.HasValue)
                {
                    _spawnAt[m.uid.Value] = OpponentBacks.position;
                }
                else if (m.from == Zones.Deck && m.to == Zones.Hand && human && m.uid.HasValue)
                {
                    _spawnAt[m.uid.Value] = HumanInfoText.transform.position;  // your deck count
                }
            }
        }

        /// <summary>Takes a card off the board (it's no longer in any zone the board shows) and animates it out.</summary>
        void Leave(CardView view, System.Func<CardView, Sequence> animation)
        {
            _cards.Remove(view.Uid);
            _zoneOf.Remove(view.Uid);
            view.Input.Handler = null;
            view.Rect.DOKill();
            view.transform.SetParent(TopLayer, true);
            animation(view).OnComplete(() => Destroy(view.gameObject));
        }

        static Sequence FlyInto(CardView view, RectTransform target)
        {
            var seq = DOTween.Sequence();
            seq.Append(view.Rect.DOMove(target.position, 0.4f).SetEase(Ease.InCubic));
            seq.Join(view.Rect.DOScale(0.15f, 0.4f).SetEase(Ease.InCubic));
            return seq;
        }

        Sequence Defeat(CardView view)
        {
            FloatText(view.Rect.position + Vector3.up * 30f * Root.lossyScale.y, UiText.Defeated, Palette.Health);
            var seq = DOTween.Sequence();
            seq.Append(view.Visual.DOShakeAnchorPos(0.3f, 10f, 24));
            seq.Append(view.Group.DOFade(0f, 0.35f));
            seq.Join(view.Rect.DOScale(view.Rect.localScale * 0.8f, 0.35f));
            return seq;
        }

        /// <summary>Anything else that left the board (e.g. a mulligan put-back) fades out quietly.</summary>
        void RemoveCardsNotIn(HashSet<int> seen, bool animate)
        {
            var gone = new List<int>();
            foreach (var kv in _cards)
                if (!seen.Contains(kv.Key)) gone.Add(kv.Key);
            foreach (int uid in gone)
            {
                var view = _cards[uid];
                if (!animate)
                {
                    _cards.Remove(uid);
                    _zoneOf.Remove(uid);
                    Destroy(view.gameObject);
                    continue;
                }
                Leave(view, v =>
                {
                    var seq = DOTween.Sequence();
                    seq.Append(v.Group.DOFade(0f, 0.3f));
                    return seq;
                });
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

        // --- effects

        void FlyCardBack(RectTransform from, RectTransform to)
        {
            var back = Instantiate(CardBackTemplate, TopLayer);
            back.SetActive(true);
            var rt = (RectTransform)back.transform;
            rt.position = from.position;
            var seq = DOTween.Sequence();
            seq.Append(rt.DOMove(to.position, 0.45f).SetEase(Ease.InOutCubic));
            seq.Join(rt.DOScale(0.3f, 0.45f).SetEase(Ease.InCubic));
            seq.OnComplete(() => Destroy(back));
        }

        void FloatText(Vector3 world, string text, Color colour)
        {
            var rt = Ui.Node("Float", TopLayer);
            rt.sizeDelta = new Vector2(200, 40);
            rt.position = world;
            var label = Ui.Display(rt, text, 26);
            label.color = colour;
            var seq = DOTween.Sequence();
            seq.Append(rt.DOAnchorPosY(rt.anchoredPosition.y + 50f, 0.9f).SetEase(Ease.OutCubic));
            seq.Insert(0.5f, DOTween.To(() => label.alpha, x => label.alpha = x, 0f, 0.4f));  // TMP tweens are DOTween Pro only
            seq.OnComplete(() => Destroy(rt.gameObject));
        }

        // --- HUD

        void SetVp(RectTransform fill, float fullWidth, TMP_Text label, int vp, bool animate)
        {
            float t = Mathf.Clamp01(vp / (float)VpToWin);
            var size = new Vector2(fullWidth * t, fill.sizeDelta.y);
            fill.DOKill();
            fill.gameObject.SetActive(t > 0f);
            if (animate) fill.DOSizeDelta(size, 0.5f).SetEase(Ease.OutCubic);
            else fill.sizeDelta = size;
            label.text = $"{vp}/{VpToWin}";
            if (fill == HumanVpFill) _vpGain.gameObject.SetActive(false);
        }

        void SetGems(RectTransform gems, TMP_Text label, PlayerState p)
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
                var rim = gem.GetChild(1);
                rim.GetComponent<Image>().color = Palette.Outline;
                rim.localScale = Vector3.one;
                if (gem.childCount > 2) gem.GetChild(2).gameObject.SetActive(ready);
            }
            label.text = $"{p.energy_ready}/{p.energy_total}";
            if (gems == HumanGems) _dashedGem.gameObject.SetActive(false);
        }

        static string Initials(string name)
        {
            if (string.IsNullOrEmpty(name)) return "?";
            return name.Length <= 2 ? name.ToUpperInvariant() : name.Substring(0, 2).ToUpperInvariant();
        }
    }
}
