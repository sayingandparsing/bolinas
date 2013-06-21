from lib.cfg import NonterminalLabel
from lib.hgraph.hgraph import Hgraph
from lib.hgraph.new_graph_description_parser import ParserError, LexerError
from lib.tree import Tree
from lib import log
from lib.exceptions import InputFormatException, BinarizationException, GrammarError
#from lib import util
import sys
import cPickle as pickle
from collections import defaultdict as ddict
import re
import StringIO

def parse_string(s):
    tokens = s.strip().split()
    res = []
    nt_index = 0
    for t in tokens:
        if "$" in t: 
            new_token = NonterminalLabel.from_string(t)
            if not new_token.index:
                new_token.index = "_%i" % nt_index
                nt_index = nt_index + 1
        else: 
            new_token = t
        res.append(new_token)
    return res            

class Grammar(dict):


    def __init__(self, nodelabels = False):
        self.nodelabels = nodelabels  
 
    @classmethod
    def load_from_file(cls, in_file, reverse = False, nodelabels = False):
        """
        Loads a SHRG grammar from the given prefix. 
        See documentation for format details.
        """    

        output = Grammar(nodelabels = nodelabels)

        rule_count = 1
        line_count = 0
        is_synchronous = False

        rhs1_type = None
        rhs2_type = None
        GRAPH_FORMAT = "hypergraph" 
        STRING_FORMAT = "string"
        TREE_FORMAT = "tree"

        buf = StringIO.StringIO() 

        for line in in_file: 
            line_count += 1
            l = line.strip()
            if l:
                if "#" in l: 
                    content, comment = l.split("#",1)
                else: 
                    content = l
                buf.write(content.strip())
                if ";" in content:
                    rulestring = buf.getvalue()
                    try:
                        content, weights = rulestring.split(";",1)
                        weight = 1.0 if not weights else float(weights)
                    except:
                        raise GrammarError, \
            "Line %i, Rule %i: Error near end of line." % (line_count, rule_count)
                    
                    lhs, rhsstring = content.split("->")
                    lhs = lhs.strip()
                    if "|" in rhsstring:
                        if not is_synchronous and rule_count > 1:
                            raise GrammarError,\
           "Line %i, Rule %i: All or none of the rules need to have two RHSs." % (line_count, rule_count)
                        is_synchronous = True
                        try:
                            rhs1,rhs2 = rhsstring.split("|")
                        except:
                            raise GrammarError,"Only up to two RHSs are allowed in grammar file."
                    else: 
                        if is_synchronous and rule_count > 0:
                            raise ParserError,\
            "Line %i, Rule %i: All or none of the rules need to have two RHSs." % (line_count, rule_count)
                        is_synchronous = False
                        rhs1 = rhsstring
                        rhs2 = None                               
                    
                    try:    # If the first graph in the file cannot be parsed, assume it's a string
                        r1  = Hgraph.from_string(rhs1)
                        r1_nts = set([(ntlabel.label, ntlabel.index) for h, ntlabel, t in r1.nonterminal_edges()])
                        if not rhs1_type:
                            rhs1_type = GRAPH_FORMAT
                    except ParserError, e: 
                        if rhs1_type == GRAPH_FORMAT:
                           raise ParserError,\
            "Line %i, Rule %i: Could not parse graph description: %s" % (line_count, rule_count, e.message)
                        else:
                           r1 = parse_string(rhs1) 
                           nts = [t for t in r1 if type(t) is NonterminalLabel]
                           r1_nts = set([(ntlabel.label, ntlabel.index) for ntlabel in nts])
                           rhs1_type = STRING_FORMAT
  
                    if is_synchronous: 
                        try:    # If the first graph in the file cannot be parsed, assume it's a string
                            r2  = Hgraph.from_string(rhs2)
                            r2_nts = set([(ntlabel.label, ntlabel.index) for h, ntlabel, t in r2.nonterminal_edges()])
                            if not rhs2_type:
                                rhs2_type = GRAPH_FORMAT
                        except ParserError, e: 
                            if rhs2_type == GRAPH_FORMAT:
                               raise ParserError,\
                "Line %i, Rule %i: Could not parse graph description: %s" % (line_count, rule_count, e.message)
                            else:
                               r2 = parse_string(rhs2) 
                               nts = [t for t in r2 if type(t) is NonterminalLabel]
                               r2_nts = set([(ntlabel.label, ntlabel.index) for ntlabel in nts])
                               rhs2_type = STRING_FORMAT

                        # Verify that nonterminals match up
                        if not r1_nts == r2_nts:
                            raise GrammarError, \
            "Line %i, Rule %i: Nonterminals do not match between RHSs." % (line_count, rule_count)
                    else: 
                        r2 = None
                    if is_synchronous and reverse: 
                        output[rule_count] = Rule(rule_count, lhs, weight, r2, r1, nodelabels = nodelabels) 
                    else: 
                        output[rule_count] = Rule(rule_count, lhs, weight, r1, r2, nodelabels = nodelabels) 
                    buf = StringIO.StringIO() 
                    rule_count += 1
        output.is_synchronous = is_synchronous
        if is_synchronous and reverse:
            output.rhs1_type, output.rhs2_type = rhs2_type, rhs1_type
        else: 
            output.rhs1_type, output.rhs2_type = rhs1_type, rhs2_type

        return output 


class Rule(object):

  @classmethod
  def normalize_weights(cls, grammar):
    """
    Reweights the given grammar _conditionally_, so that the weights of all
    rules with the same right hand side sum to 1.
    """
    norms = ddict(lambda:0.0)
    for rule in grammar.values():
      norms[rule.symbol] += rule.weight
    ngrammar = {}
    for rule_id, rule in grammar.items():
      nrule = rule.reweight(rule.weight / norms[rule.symbol])
      ngrammar[rule_id] = nrule
    return ngrammar

  def __init__(self, rule_id, symbol, weight, rhs1, rhs2, rhs1_visit_order =
      None, rhs2_visit_order = None, original_index = None, nodelabels = False):
    self.rule_id = rule_id
    self.symbol = symbol
    self.weight = weight
    self.rhs1 = rhs1
    self.rhs2 = rhs2
    self.nodelabels = nodelabels
    #if isinstance(rhs2, Tree):
    #  self.string = rhs2.leaves()
    #else:
    if isinstance(rhs1, list):
        self.string = rhs1 

    # Set default visit order: canonical order of hyperedges or string tokens left-to-right
    # Also determine if this RHS is a terminal
    if isinstance(rhs1, Hgraph):
        assert len(rhs1.roots) == 1
        self.is_terminal = not any(rhs1.nonterminal_edges())
        self.rhs1_visit_order = rhs1_visit_order if rhs1_visit_order is not None else range(len(rhs1.triples(nodelabels = nodelabels)))
    else: 
        self.is_terminal = not any([t for t in rhs1 if type(t) is NonterminalLabel])
        self.rhs1_visit_order = rhs1_visit_order if rhs1_visit_order is not None else range(len(rhs1)) 

    if self.rhs2 is not None:
        if isinstance(rhs2, Hgraph):
            self.rhs2_visit_order = rhs2_visit_order if rhs2_visit_order is not None else range(len(rhs2.triples(nodelabels = nodelabels)))
        else: 
            self.rhs2_visit_order = rhs2_visit_order if rhs2_visit_order is not None else range(len(rhs2)) 

    if original_index != None:
      self.original_index = original_index


  def reweight(self, nweight):
    return Rule(self.rule_id, self.symbol, nweight, self.rhs1, self.parse, \
        self.rhs1_visit_order, self.rhs2_visit_order)

  def canonicalize_amr(self):
    return Rule(self.rule_id, self.symbol, self.weight,
        self.amr.clone_canonical(), self.parse, self.rhs1_visit_order,
        self.rhs2_visit_order)

  def __repr__(self):
    return 'Rule(%d,%s)' % (self.rule_id, self.symbol)

  def __hash__(self):
    return self.rule_id

  def __eq__(self, other):
    return isinstance(other, Rule) and self.rule_id == other.rule_id

  def binarize(self, next_id):
    oid = next_id
    tree = self.parse
    amr = self.amr

    # handle all-terminal rules
    if not any(s[0] == '#' for s in tree.leaves()):
      return [Rule(next_id, self.symbol, self.weight, self.amr, self.parse,
        self.rhs1_visit_order, self.rhs2_visit_order)], next_id + 1

    # handle rules containing nonterminals
    rules = []
    try:
      tree, amr, at_rules, next_id = self.collapse_amr_terminals(tree, amr,
          next_id)
      rules += at_rules

      string = tree.leaves()

      string, amr, st_rules, next_id = self.collapse_string_terminals(string,
          amr, next_id)
      rules += st_rules

      string, amr, nt_rules, next_id = self.merge_string_nonterminals(string,
          amr, next_id)
      rules += nt_rules
    except BinarizationException:
      log.warn('Unbinarizable rule!')
      return None, oid
    
    # sanity check---did we completely binarize the rule?
    assert len(string) == 1
    assert len(amr.triples()) == 1
    rules.append(Rule(next_id + 1, self.symbol, self.weight, amr, string[0]))
    return rules, next_id + 2

  def binarize_tree(self, next_id):
    oid = next_id
    tree = self.parse
    amr = self.amr

    # handle all-terminal rules
    if not any(s[0] == '#' for s in tree.leaves()):
      return [Rule(next_id, self.symbol, self.weight, self.amr, self.parse,
        self.rhs1_visit_order, self.rhs2_visit_order)], next_id + 1

    # handle rules containing nonterminals
    rules = []
    try:
      tree, amr, at_rules, next_id = self.collapse_amr_terminals(tree, amr,
          next_id)
      rules += at_rules

      tree, amr, ts_rules, next_id = self.merge_tree_symbols(tree, amr, next_id)
      rules += ts_rules
    except BinarizationException:
      log.warn('Unbinarizable rule!')
      return None, oid

    # sanity check as above
    assert isinstance(tree, str)
    assert len(amr.triples()) == 1
    rules.append(Rule(next_id + 1, self.symbol, self.weight, amr, tree))
    return rules, next_id + 2

  def terminal_search(self, root, triples):
    """
    Searches for terminal edges reachable from the given root edge without
    passing through a nonterminal edge.
    """
    stack = []
    for r in root[2]:
      stack.append(r)
    out = set()
    while stack:
      top = stack.pop()
      children = [t for t in triples if t[0] == top and not isinstance(t[1],
        NonterminalLabel) and t not in out]
      for c in children:
        out.add(c)
        for t in c[2]:
          stack.append(t)
    return out

  def collapse_amr_terminals(self, tree, amr, next_id):
    """
    Creates new rules by merging terminal subgraphs with their closest
    nonterminal edge.
    """
    # triples returns in breadth-first order, so first triples in the list are
    # closest to the root of the AMR
    nonterminals = list(reversed([t for t in amr.triples() if isinstance(t[1],
      NonterminalLabel)]))
    rules = []
    first = True
    while nonterminals:
      nt = nonterminals.pop()
      # in general, we will attach to a given nonterminal edge all of the
      # terminal edges reachable from its tail nodes
      attached_terminals = self.terminal_search(nt, amr.triples())
      if first:
        # we still have to handle terminal edges that are higher than any
        # nonterminal edge
        # because the first nonterminal edge is closest to the root of the AMR,
        # it must be reachable from the root without passing through any other
        # nonterminal, so we can attach all the high terminals (those reachable
        # from the root) to the first nonterminal
        attached_terminals |= self.terminal_search(amr.root_edges()[0],
            amr.triples())
        attached_terminals |= {amr.root_edges()[0]}
        first = False
      # don't bother making a rule when there's nothing to collapse
      if not attached_terminals:
        continue

      rule_amr = Hgraph.from_triples({nt} | attached_terminals)
      rule_tree = str(nt[1])

      assert len(rule_amr.roots) == 1

      new_rule, tree, amr, next_id = self.make_rule(tree, amr, rule_tree,
          rule_amr, next_id)
      rules.append(new_rule)

    return tree, amr, rules, next_id

  def make_fictitious_tree(self, string, rule_string):
    """
    Creates a tree in which rule_string is a single constituent.
    When doing string binarization, we sometimes need to merge edges that
    violate the bracketing constraints of the parse tree. In this case, rather
    than writing a duplicate version of make_rule that handles strings instead
    of trees, we simply hallucinate a parse tree with an acceptable structure.
    """
    start = 0
    while start < len(string):
      piece = string[start:start+len(rule_string)]
      if piece == rule_string:
        break
      start += 1
    assert start != len(string)
    end = start + len(rule_string)

    children = []
    if string[:start]:
      children.append(Tree('W', string[:start]))
    children.append(Tree('X', rule_string))
    if string[end:]:
      children.append(Tree('Y', string[end:]))
    return Tree('ROOT', children)

  def collapse_string_terminals(self, string, amr, next_id):
    """
    Creates new rules by merging terminal tokens with their closest nonterminal.
    All terminals attach to the left (except for terminals left of the first
    nonterminal, which attach right).
    """
    nonterminals = list(reversed([t for t in string if t[0] == '#']))
    rules = []
    # attach first terminals to the right
    slice_from = 0

    while nonterminals:
      nt = nonterminals.pop()
      if nonterminals:
        slice_to = string.index(nonterminals[-1])
      else:
        slice_to = len(string)
      if slice_to - slice_from == 1:
        # there are no terminals to attach here, so skip ahead
        slice_from = slice_to
        continue

      rule_string = string[slice_from:slice_to]
      nt_edge_l = [e for e in amr.triples(nodelabels = self.nodelabels) if str(e[1]) == nt]
      assert len(nt_edge_l) == 1
      rule_amr = Hgraph.from_triples(nt_edge_l)

      # hallucinate a tree with acceptable structure for make_rule
      fictitious_tree = self.make_fictitious_tree(string, rule_string)
      new_rule, tree, amr, next_id = self.make_rule(fictitious_tree, amr,
          Tree('X', rule_string), rule_amr, next_id)
      string = tree.leaves()
      rules.append(new_rule)

      slice_from = slice_from + 1

    return string, amr, rules, next_id

  def merge_string_nonterminals(self, string, amr, next_id):
    """
    Binarizes a string-graph pair consisting entirely of nonterminals, ensuring
    correct visit order for parsing.
    """
    rules = []
    stack = []
    tokens = list(reversed([s for s in string if s]))
    # standard shift-reduce binarization algorithm
    # TODO add citation after paper is published
    while tokens:
      next_tok = tokens.pop()
      next_tok_triple_l = [t for t in amr.triples() if str(t[1]) == next_tok]
      assert len(next_tok_triple_l) == 1
      next_tok_triple = next_tok_triple_l[0]
      if not stack:
        stack.append(next_tok)
        continue
      stack_top = stack.pop()
      stack_top_triple = [t for t in amr.triples() if str(t[1]) == stack_top][0]

      if (stack_top_triple[0] not in next_tok_triple[2]) and \
          (next_tok_triple[0] not in stack_top_triple[2]):
        # can't merge, so shift
        stack.append(stack_top)
        stack.append(next_tok)
        continue

      # can merge, so reduce
      rule_amr = Hgraph.from_triples([stack_top_triple, next_tok_triple])
      assert len(rule_amr.roots) == 1

      rule_string = [stack_top, next_tok]
      fictitious_tree = self.make_fictitious_tree(string, rule_string)
      new_rule, tree, amr, next_id = self.make_rule(fictitious_tree, amr,
          Tree('X', rule_string), rule_amr, next_id)
      string = tree.leaves()
      tokens.append('#%s' % new_rule.symbol)
      rules.append(new_rule)

    if len(stack) > 1:
      raise BinarizationException

    return string, amr, rules, next_id

  def merge_tree_symbols(self, tree, amr, next_id):
    """
    Binarizes a tree-graph pair according to the binariziation dictated by the
    tree. WILL FAIL OFTEN IF TREE IS NOT BINARIZED.
    """
    rules = []
    while True:
      if not isinstance(tree, Tree):
        assert len(amr.triples()) == 1
        return tree, amr, rules, next_id

      # a collapsible subtree consists of
      # 1. many terminals
      # 2. one nonterminal and many terminals
      # 3. two nonterminals
      collapsible_subtrees = []
      for st in tree.subtrees():
        terminals = [t for t in st.leaves() if t[0] == '#']
        if len(terminals) == 1:
          collapsible_subtrees.append(st)
        elif len(terminals) == 2 and len(st.leaves()) == 2:
          collapsible_subtrees.append(st)

      # if there are no subtrees to collapse, this rule isn't binarizable
      if len(collapsible_subtrees) == 0:
        raise BinarizationException

      rule_tree = max(collapsible_subtrees, key=lambda x: x.height())
      terminals = [t for t in rule_tree.leaves() if t[0] == '#']
      rule_edge_l = [t for t in amr.triples() if str(t[1]) in terminals]
      rule_amr = Hgraph.from_triples(rule_edge_l)
      # if the induced graph is disconnected, this rule isn't binarizable
      if len(rule_amr.roots) != 1:
        raise BinarizationException

      new_rule, tree, amr, next_id = self.make_rule(tree, amr, rule_tree,
          rule_amr, next_id)
      rules.append(new_rule)

    return tree, amr, rules, next_id

  def collapse_constituent(self, tree, constituent, label):
    if tree == constituent:
      return str(label)
    if not isinstance(tree, Tree):
      return tree
    n_tree = Tree(tree.node, [self.collapse_constituent(subtree, constituent,
      label) for subtree in tree])
    return n_tree

  def make_rule(self, tree, amr, rule_tree, rule_amr, next_id):
    """
    Helper method to create a new rule, and update the structure of the source
    tree and amr with the rule "unapplied".
    """
    new_rule_id = next_id + 1
    new_symbol = '%d__%d' % (self.rule_id, new_rule_id)

    if isinstance(rule_tree, Tree):
      rule_string = rule_tree.leaves()
    else:
      rule_string = [rule_tree]

    amr_t_indices = []
    amr_nt_indices = []
    for i in range(len(rule_amr.triples())):
      if isinstance(rule_amr.triples()[i][1], NonterminalLabel):
        amr_nt_indices.append(i)
      else:
        amr_t_indices.append(i)
    rhs1_visit_order = amr_t_indices + amr_nt_indices

    rhs2_visit_order = range(len(rule_string))
    string_t_indices = [s for s in rule_string if s[0] == '#']

    # choose visit order correctly for multi-nonterminal rules
    if len(amr_t_indices) == 0 and len(string_t_indices) == 0:
      assert rhs2_visit_order == [0,1]
      assert rhs1_visit_order == [0,1]
      if rule_string[0] != str(rule_amr.triples()[0][1]):
        rhs1_visit_order = [1,0]

    # determine external nodes
    external = []
    for node in rule_amr:
      if node in amr.external_nodes:
        external.append(node)
      adjacent_edges = amr.in_edges(node) + amr.out_edges(node)
      if any(e not in rule_amr.triples() for e in adjacent_edges):
        external.append(node)
    external = list(set(external))
    rule_root = list(rule_amr.roots)[0]
    if rule_root in external:
      external.remove(rule_root)
    if len(external) == 0:
      external.append(rule_amr.find_leaves()[0][2][0])
    rule_amr.external_nodes = external

    # create new rule
    new_rule = Rule(new_rule_id, new_symbol, 1, rule_amr, rule_tree,
        rhs1_visit_order, rhs2_visit_order)

    # unapply new rule
    label = NonterminalLabel(new_symbol)
    o_amr = amr.collapse_fragment(rule_amr, label)
    o_tree = self.collapse_constituent(tree, rule_tree, label)

    if len(o_amr.external_nodes) == 0:
      o_amr.external_nodes.append(o_amr.find_leaves()[0])

    return new_rule, o_tree, o_amr, next_id+1
