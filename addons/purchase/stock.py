# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2004-2010 Tiny SPRL (<http://tiny.be>).
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

from openerp.osv import fields, osv
from openerp import netsvc
from openerp.tools.translate import _

class stock_move(osv.osv):
    _inherit = 'stock.move'
    _columns = {
        'purchase_line_id': fields.many2one('purchase.order.line',
            'Purchase Order Line', ondelete='set null', select=True,
            readonly=True),
    }

    def write(self, cr, uid, ids, vals, context=None):
        if isinstance(ids, (int, long)):
            ids = [ids]
        res = super(stock_move, self).write(cr, uid, ids, vals, context=context)
        from openerp import workflow
        for id in ids:
            workflow.trg_trigger(uid, 'stock.move', id, cr)
        return res

#
# Inherit of picking to add the link to the PO
#
class stock_picking(osv.osv):
    _inherit = 'stock.picking'
    _columns = {
        'purchase_id': fields.many2one('purchase.order', 'Purchase Order',
            ondelete='set null', select=True),
    }

    _defaults = {
        'purchase_id': False,
    }

    # TODO: Invoice based on receptions
    # Here is how it should work:
    #   On a draft invoice, allows to select purchase_orders (many2many_tags)
    # This fills in automatically PO lines or from related receptions if any

class stock_warehouse(osv.osv):
    _inherit = 'stock.warehouse'
    _columns = {                
        'can_buy_for_resupply': fields.boolean('Can buy for resupply this warehouse'),
        'buy_pull_id': fields.many2one('procurement.rule', 'BUY rule'),    
    }
    _defaults= {
        'can_buy_for_resupply': True,
        'buy_pull_id' : False
    }
            
    def _get_buy_pull_rule(self, cr, uid, warehouse, context=None):    
        if not warehouse.can_buy_for_resupply:
          return False
#             
        route_obj = self.pool.get('stock.location.route')        
        data_obj = self.pool.get('ir.model.data')
        try:
            buy_route_id = data_obj.get_object_reference(cr, uid, 'stock', 'route_warehouse0_buy')[1]
        except:
            buy_route_id = route_obj.search(cr, uid, [('name', 'like', _('Buy'))], context=context)
            buy_route_id = buy_route_id and buy_route_id[0] or False
        if not buy_route_id:
            raise osv.except_osv(_('Error!'), _('Can\'t find any generic Buy route.'))                
        
        dest_loc = warehouse.in_type_id
        return {
            'name': warehouse.name + ': ' + _(' Buy') + ' -> ' + dest_loc.name,            
            'location_id': warehouse.wh_input_stock_loc_id.id,
            'route_id': buy_route_id,
            'action': 'move',
            'picking_type_id': dest_loc.id,
            'procure_method': 'make_to_order',
            'active': True,
        }
        
    def create_routes(self, cr, uid, ids, warehouse, context=None):        
        pull_obj = self.pool.get('procurement.rule')                   
        res = super(stock_warehouse, self).create_routes(cr, uid, ids, warehouse, context=context)
        buy_pull_vals = self._get_buy_pull_rule(cr, uid, warehouse, context=context)
        if buy_pull_vals:
            buy_pull_id = pull_obj.create(cr, uid, buy_pull_vals, context=context)
            res['buy_pull_id'] = buy_pull_id
        else:
            res['buy_pull_id'] = False
        return res
        
    
    def write(self, cr, uid, ids, vals, context=None):
        pull_obj = self.pool.get('procurement.rule')
        if isinstance(ids, (int, long)):
            ids = [ids]
            
        #only if update and checkbox have changed !
        if not vals.get("can_buy_for_resupply",None) is None:           
            
            if vals.get("can_buy_for_resupply",False):
                for warehouse in self.browse(cr, uid, ids, context=context):
                    if not warehouse.buy_pull_id:
                        warehouse.can_buy_for_resupply = True
                        buy_pull_vals = self._get_buy_pull_rule(cr, uid, warehouse, context=context)
                        buy_pull_id = pull_obj.create(cr, uid, buy_pull_vals, context=context)
                        vals['buy_pull_id'] = buy_pull_id
            else:
                 for warehouse in self.browse(cr, uid, ids, context=context):
                    if warehouse.buy_pull_id:
                          buy_pull_id = pull_obj.unlink(cr, uid, warehouse.buy_pull_id.id, context=context)
                          vals['buy_pull_id'] = False
                
        return super(stock_warehouse,self).write(cr, uid, ids, vals, context=None)
        
    def get_all_routes_for_wh(self, cr, uid, warehouse, context=None):
        all_routes = super(stock_warehouse,self).get_all_routes_for_wh(cr,uid,warehouse,context=context)
        if warehouse.can_buy_for_resupply and warehouse.buy_pull_id and warehouse.buy_pull_id.route_id:
            all_routes += [warehouse.buy_pull_id.route_id.id]        
        return all_routes

    def _get_all_products_to_resupply(self, cr, uid, warehouse, context=None):
        res = super(stock_warehouse,self)._get_all_products_to_resupply(cr, uid, warehouse, context=context)
        if warehouse.buy_pull_id and warehouse.buy_pull_id.route_id:
            for product_id in res:
                for route in self.pool.get('product.product').browse(cr, uid, product_id, context=context).route_ids:                       
                    if route.id == warehouse.buy_pull_id.route_id.id:                    
                        res.remove(product_id)                    
                        break                
        return res