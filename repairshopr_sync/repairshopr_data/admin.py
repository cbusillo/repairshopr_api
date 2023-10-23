from django.contrib import admin

from .models import Customer, Estimate, Invoice, Payment, Product, Ticket, User
from .models.estimate import EstimateLineItem

admin.site.register(Invoice)
admin.site.register(Payment)
admin.site.register(User)


class CustomerAdmin(admin.ModelAdmin):
    list_display = ("id", "business_then_name", "phone", "email")


class EstimateLineItemInline(admin.TabularInline):  # or admin.StackedInline for a different layout
    model = EstimateLineItem
    extra = 1  # Number of empty forms displayed


class EstimateAdmin(admin.ModelAdmin):
    list_display = ("id", "customer_business_then_name", "total")
    inlines = [EstimateLineItemInline]


admin.site.register(Estimate, EstimateAdmin)
admin.site.register(Customer, CustomerAdmin)

admin.site.register(Product)
admin.site.register(Ticket)
